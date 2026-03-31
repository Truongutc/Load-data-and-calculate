import pandas as pd
import os
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

class StorageManager:
    def __init__(self, base_dir="data_storage"):
        self.base_dir = Path(base_dir)
        self.prices_dir = self.base_dir / "prices"
        self.indicators_dir = self.base_dir / "indicators"
        self.analysis_dir = self.base_dir / "analysis"
        
        # Ensure directories exist
        for d in [self.prices_dir, self.indicators_dir, self.analysis_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _get_price_path(self, ticker):
        return self.prices_dir / f"{ticker.upper()}.parquet"

    def _get_indicators_path(self, ticker):
        return self.indicators_dir / f"{ticker.upper()}.parquet"

    def _get_analysis_path(self, ticker):
        return self.analysis_dir / f"{ticker.upper()}.json"

    def sync_prices(self, ticker, new_df, source):
        """
        Sync incoming price data with SSoT logic: CSV > API.
        Returns T_min (earliest date changed) if a change occurred, else None.
        """
        if new_df.empty: return None
        ticker = ticker.upper()
        
        target_path = self._get_price_path(ticker)
        
        # 1. Normalize New Data
        work_df = new_df.copy()
        work_df['Date'] = pd.to_datetime(work_df['Date'])
        work_df['source'] = source
        work_df['updated_at'] = datetime.now()
        
        # Canonical columns
        cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'source', 'updated_at']
        work_df = work_df[[c for c in cols if c in work_df.columns]]
        
        if not target_path.exists():
            work_df.sort_values('Date').to_parquet(target_path, index=False)
            return work_df['Date'].min()

        # 2. Load Existing & Merge
        try:
            old_df = pd.read_parquet(target_path)
            old_df['Date'] = pd.to_datetime(old_df['Date'])
        except Exception as e:
            logger.error(f"Error reading existing parquet for {ticker}: {e}")
            old_df = pd.DataFrame()

        if old_df.empty:
            work_df.sort_values('Date').to_parquet(target_path, index=False)
            return work_df['Date'].min()

        # 3. MERGE LOGIC: CSV > API
        # Combine all dates
        combined = pd.concat([old_df, work_df], ignore_index=True)
        
        # Sort by Date and Source Hierarchy
        # We want 'CSV' to be 'greater than' 'API' in terms of priority if dates collide
        # Custom sort key: CSV -> 1, API -> 0
        combined['_priority'] = combined['source'].apply(lambda x: 1 if str(x).upper() == 'CSV' else 0)
        
        # Group by Date and take the one with highest priority, then most recent update
        # If both are CSV, take the last one provided
        final_df = combined.sort_values(['Date', '_priority', 'updated_at'], ascending=[True, True, True])
        final_df = final_df.drop_duplicates(subset=['Date'], keep='last').drop(columns=['_priority'])
        
        # 4. Detect T_min (Smallest date where price changed)
        # We only re-calculate if Price (OHLCV) changed. source/updated_at changes don't need re-calc.
        price_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        # Merge old and new on Date to compare
        merged = pd.merge(old_df[['Date'] + price_cols], final_df[['Date'] + price_cols], 
                          on='Date', how='outer', suffixes=('_old', '_new'))
        
        # Use a small epsilon for float comparison to handle rounding drift
        changed_mask = False
        for col in price_cols:
            diff = (merged[f'{col}_old'] - merged[f'{col}_new']).abs()
            # If one is NaN and other is not, it's a change
            nan_change = merged[f'{col}_old'].isna() != merged[f'{col}_new'].isna()
            changed_mask |= (diff > 0.0001) | nan_change
            
        changed_dates = merged.loc[changed_mask, 'Date']
        
        if changed_dates.empty:
            # Check if we added NEW dates at the end
            new_dates = set(final_df['Date']) - set(old_df['Date'])
            if new_dates:
                t_min = min(new_dates)
            else:
                return None # No real change
        else:
            t_min = changed_dates.min()

        final_df.sort_values('Date').to_parquet(target_path, index=False)
        return t_min

    def get_last_date(self, ticker=None):
        if ticker:
            path = self._get_price_path(ticker)
            if path.exists():
                df = pd.read_parquet(path, columns=['Date'])
                return pd.to_datetime(df['Date']).max()
            return None
        
        # Global last date across all tickers
        all_dates = []
        for p in self.prices_dir.glob("*.parquet"):
            df = pd.read_parquet(p, columns=['Date'])
            if not df.empty:
                all_dates.append(df['Date'].max())
        
        return max(all_dates) if all_dates else None

    def get_all_tickers(self):
        return [p.stem for p in self.prices_dir.glob("*.parquet")]

    def load_ticker_data(self, ticker):
        p_path = self._get_price_path(ticker)
        i_path = self._get_indicators_path(ticker)
        
        if not p_path.exists(): return None
        
        prices = pd.read_parquet(p_path)
        prices['Date'] = pd.to_datetime(prices['Date'])
        
        if i_path.exists():
            indicators = pd.read_parquet(i_path)
            indicators['Date'] = pd.to_datetime(indicators['Date'])
            # Merge
            df = pd.merge(prices, indicators, on='Date', how='left')
            # Handle potential duplicate columns from merge if any (though shouldn't happen with correct storage)
            df = df.loc[:, ~df.columns.duplicated()]
            return df.sort_values('Date').reset_index(drop=True)
        
        return prices.sort_values('Date').reset_index(drop=True)

    def save_indicators(self, ticker, df):
        """Save indicators (non-price columns) to parquet."""
        price_cols = ['Open', 'High', 'Low', 'Close', 'Volume', 'source', 'updated_at']
        # We also want to exclude Ticker if it's there
        exclude = price_cols + ['Ticker', 'Date']
        
        indicator_cols = ['Date'] + [c for c in df.columns if c not in exclude]
        
        # Deduplicate column names just in case there are duplicates in the dataframe itself
        indicator_cols = list(dict.fromkeys(indicator_cols))
        
        to_save = df[indicator_cols].copy()
        to_save['Date'] = pd.to_datetime(to_save['Date'])
        
        i_path = self._get_indicators_path(ticker)
        to_save.sort_values('Date').to_parquet(i_path, index=False)

    def save_analysis(self, ticker, results):
        import json
        import numpy as np
        
        def sanitize(obj):
            if isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize(v) for v in obj]
            elif isinstance(obj, (np.bool_, np.integer, np.floating)):
                return obj.item()
            elif isinstance(obj, (pd.Timestamp, datetime)):
                return obj.strftime('%Y-%m-%d')
            return obj

        clean_results = sanitize(results)
        # Drop heavy dataframe if accidentally passed
        if 'df' in clean_results: del clean_results['df']
        
        path = self._get_analysis_path(ticker)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(clean_results, f, ensure_ascii=False, indent=2)

    def load_latest_analysis(self, ticker):
        import json
        path = self._get_analysis_path(ticker)
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def get_ticker_counts_for_dates(self, dates: list) -> dict:
        """
        Return a dictionary of {date_str: count} for a list of dates.
        Scans all parquet files to count tickers per date.
        """
        counts = {d: 0 for d in dates}
        target_dates = [pd.to_datetime(d) for d in dates]
        
        for p in self.prices_dir.glob("*.parquet"):
            try:
                # Only read Date column to be fast
                df = pd.read_parquet(p, columns=['Date'])
                if df.empty: continue
                
                df_dates = pd.to_datetime(df['Date'])
                # Count how many of our target dates exist in this ticker's file
                exists = df_dates.isin(target_dates)
                if exists.any():
                    matched_dates = df_dates.loc[exists].dt.strftime('%Y-%m-%d').unique()
                    for d_str in matched_dates:
                        counts[d_str] += 1
            except Exception as e:
                logger.error(f"Error checking dates in {p.name}: {e}")
                
        return counts

    def delete_specific_dates(self, dates_to_delete: list):
        """
        Remove rows for specific dates from ALL price and indicator parquet files.
        """
        if not dates_to_delete: return
        
        target_ts = [pd.to_datetime(d) for d in dates_to_delete]
        logger.info(f"Deleting specific dates from storage: {dates_to_delete}")
        
        # 1. Clean Prices
        for p in self.prices_dir.glob("*.parquet"):
            try:
                df = pd.read_parquet(p)
                df['Date'] = pd.to_datetime(df['Date'])
                original_len = len(df)
                
                df = df[~df['Date'].isin(target_ts)]
                if len(df) < original_len:
                    df.to_parquet(p, index=False)
            except Exception as e:
                logger.error(f"Error deleting dates from price {p.name}: {e}")

        # 2. Clean Indicators
        for p in self.indicators_dir.glob("*.parquet"):
            try:
                df = pd.read_parquet(p)
                df['Date'] = pd.to_datetime(df['Date'])
                original_len = len(df)
                
                df = df[~df['Date'].isin(target_ts)]
                if len(df) < original_len:
                    df.to_parquet(p, index=False)
            except Exception as e:
                logger.error(f"Error deleting dates from indicator {p.name}: {e}")
