"""
Module 1 – Data Loader
======================
Reads OHLCV CSV files, normalizes columns, and returns clean DataFrames.
Supports single-ticker and multi-ticker CSV files.
"""

import logging
import numpy as np
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Centralized Enrichment ─────────────────────────────────────────────────────

def _donchian_mid(series_high: pd.Series, series_low: pd.Series, period: int) -> pd.Series:
    """(highest_high + lowest_low) / 2 over rolling window."""
    return (series_high.rolling(window=period).max() + series_low.rolling(window=period).min()) / 2


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enriches an OHLCV DataFrame with ALL technical indicators needed by every engine.
    
    This is the SINGLE SOURCE OF TRUTH for indicator calculation.
    All engines should call this once, then read pre-computed columns.
    
    The function is idempotent — columns that already exist are skipped.
    
    Indicators computed:
        - MA: MA10, MA20, MA50, MA100, MA200
        - Volatility: ATR14
        - Volume: AvgVolume20
        - Ichimoku: Tenkan, Kijun, Kijun65, SpanA, SpanB, Chikou, CloudTop, CloudBottom
        - Heikin Ashi: HA_Open, HA_Close, HA_Color
        - VSA helpers: Spread, Avg_Spread_20, Stopping_Vol, No_Supply, Test_Supply
    """
    if len(df) < 2:
        return df

    out = df

    # ── 1. Moving Averages ─────────────────────────────────────────────────
    for period, name in [(10, 'MA10'), (20, 'MA20'), (50, 'MA50'), (100, 'MA100'), (200, 'MA200')]:
        if name not in out.columns:
            out[name] = out['Close'].rolling(period).mean()

    # ── 2. ATR14 ───────────────────────────────────────────────────────────
    if 'ATR14' not in out.columns:
        high_low = out['High'] - out['Low']
        high_prev_close = (out['High'] - out['Close'].shift(1)).abs()
        low_prev_close = (out['Low'] - out['Close'].shift(1)).abs()
        tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        out['ATR14'] = tr.rolling(14).mean()

    # ── 3. Volume ──────────────────────────────────────────────────────────
    if 'AvgVolume20' not in out.columns:
        out['AvgVolume20'] = out['Volume'].rolling(20).mean()

    # ── 4. Ichimoku ────────────────────────────────────────────────────────
    if 'Tenkan' not in out.columns:
        out['Tenkan'] = _donchian_mid(out['High'], out['Low'], 9)
    if 'Kijun' not in out.columns:
        out['Kijun'] = _donchian_mid(out['High'], out['Low'], 26)
    if 'Kijun65' not in out.columns:
        out['Kijun65'] = _donchian_mid(out['High'], out['Low'], 65)
    if 'SpanA' not in out.columns:
        out['SpanA'] = ((out['Tenkan'] + out['Kijun']) / 2).shift(26)
    if 'SpanB' not in out.columns:
        out['SpanB'] = _donchian_mid(out['High'], out['Low'], 52).shift(26)
    if 'Chikou' not in out.columns:
        out['Chikou'] = out['Close'].shift(-26)
    if 'CloudTop' not in out.columns:
        out['CloudTop'] = out[['SpanA', 'SpanB']].max(axis=1)
    if 'CloudBottom' not in out.columns:
        out['CloudBottom'] = out[['SpanA', 'SpanB']].min(axis=1)

    # ── 5. Heikin Ashi ─────────────────────────────────────────────────────
    if 'HA_Color' not in out.columns:
        ha_close = (out['Open'] + out['High'] + out['Low'] + out['Close']) / 4
        ha_open = np.zeros(len(out))
        ha_open[0] = (out['Open'].iloc[0] + out['Close'].iloc[0]) / 2
        for i in range(1, len(out)):
            ha_open[i] = (ha_open[i-1] + ha_close.iloc[i-1]) / 2
        out['HA_Open'] = ha_open
        out['HA_Close'] = ha_close
        out['HA_Color'] = np.where(ha_close > ha_open, 'Green', 'Red')

    # ── 6. VSA Helpers ─────────────────────────────────────────────────────
    if 'Spread' not in out.columns:
        out['Spread'] = out['High'] - out['Low']
    if 'Avg_Spread_20' not in out.columns:
        out['Avg_Spread_20'] = out['Spread'].rolling(20).mean()
    if 'Stopping_Vol' not in out.columns:
        out['Stopping_Vol'] = (
            (out['Volume'] > 1.5 * out['AvgVolume20']) &
            (out['Spread'] > out['Avg_Spread_20']) &
            (out['Close'] > out['Low'] + 0.3 * out['Spread'])
        )
    if 'No_Supply' not in out.columns:
        out['No_Supply'] = (
            (out['Volume'] < 0.7 * out['AvgVolume20']) &
            (out['Spread'] < out['Avg_Spread_20']) &
            (out['Close'] < out['Open'])
        )
    if 'Test_Supply' not in out.columns:
        out['Test_Supply'] = (
            (out['Volume'] < out['AvgVolume20']) &
            (out['Spread'] < out['Avg_Spread_20'] * 0.8) &
            (out['Close'] > out['Low'] + 0.4 * out['Spread'])
        )

    return out

# ── Column name aliases accepted in input CSV ──────────────────────────────────
_COLUMN_ALIASES = {
    "date":   ["date", "time", "datetime", "ngay", "ngày", "trading_date", "dtyyyymmdd"],
    "open":   ["open", "mo_cua", "mở_cửa", "open_price"],
    "high":   ["high", "cao_nhat", "cao_nhất", "high_price"],
    "low":    ["low", "thap_nhat", "thấp_nhất", "low_price"],
    "close":  ["close", "dong_cua", "đóng_cửa", "close_price", "last"],
    "volume": ["volume", "vol", "klgd", "khoi_luong", "klgd_cp"],
    "ticker": ["ticker", "symbol", "ma_ck", "mã_ck", "stock", "code"],
}

MIN_ROWS = 2


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw CSV column names to canonical names (Date, Open, High, Low, Close, Volume, Ticker)."""
    lower_cols = {c: c.lower().strip().replace(" ", "_").replace("<", "").replace(">", "") for c in df.columns}
    df = df.rename(columns=lower_cols)

    rename_map = {}
    for canonical, aliases in _COLUMN_ALIASES.items():
        for col in df.columns:
            if col in aliases:
                rename_map[col] = canonical.capitalize() if canonical != "ticker" else "Ticker"
                break

    df = df.rename(columns=rename_map)

    # Ensure required columns exist
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}. Found: {list(df.columns)}")

    return df


def _clean_dataframe(df: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    """Parse dates, sort, handle missing data, validate row count."""
    # Parse Date
    try:
        # Convert to string and clean up potential float strings (e.g. "20231026.0")
        date_series = df["Date"].astype(str).str.replace(r"\.0$", "", regex=True)
        
        # If the strings are 8-digit YYYYMMDD, use explicit format for reliability
        if date_series.str.match(r"^\d{8}$").all():
            df["Date"] = pd.to_datetime(date_series, format="%Y%m%d")
        else:
            df["Date"] = pd.to_datetime(date_series, errors="coerce")
            
        if df["Date"].isna().any():
            # Fallback for mixed or other formats
            df["Date"] = pd.to_datetime(df["Date"], errors="raise")
            
    except Exception as exc:
        raise ValueError(f"[{ticker}] Cannot parse Date column: {exc}") from exc

    # Sort ascending
    df = df.sort_values("Date").reset_index(drop=True)

    # Drop rows where ALL price columns are NaN
    price_cols = ["Open", "High", "Low", "Close", "Volume"]
    df = df.dropna(subset=price_cols, how="all")

    # Forward-fill remaining NaN (e.g. sparse volume)
    df[price_cols] = df[price_cols].ffill()

    # Ensure numeric types
    for col in price_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows that still have NaN after ffill (e.g. leading rows)
    df = df.dropna(subset=price_cols).reset_index(drop=True)

    # Minimum row check
    if len(df) < MIN_ROWS:
        raise ValueError(
            f"[{ticker}] Insufficient data: {len(df)} rows found, minimum required is {MIN_ROWS}."
        )

    logger.info(f"[{ticker}] Loaded {len(df)} rows from {df['Date'].iloc[0].date()} to {df['Date'].iloc[-1].date()}")
    return df


def load_data(file_path: "str | list[str]") -> "pd.DataFrame | dict[str, pd.DataFrame]":
    """
    Load OHLCV CSV file(s) and return a clean DataFrame or dict of DataFrames.

    Parameters
    ----------
    file_path : str | list[str]
        Path or list of paths to the CSV file(s) containing OHLCV data.

    Returns
    -------
    pd.DataFrame
        If the CSV contains a single ticker (no 'Ticker' column or only one unique ticker).
    dict[str, pd.DataFrame]
        If the CSV contains multiple tickers keyed by ticker symbol.
    """
    try:
        if isinstance(file_path, list):
            logger.info(f"Loading data from {len(file_path)} files")
            dfs = []
            for path in file_path:
                p = Path(path)
                if p.exists() and p.suffix.lower() == ".csv":
                    dfs.append(pd.read_csv(p))
            if not dfs:
                raise ValueError("No valid CSV files found in the provided list.")
            raw = pd.concat(dfs, ignore_index=True)
        else:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            if path.suffix.lower() != ".csv":
                raise ValueError(f"Expected a CSV file, got: {path.suffix}")
            logger.info(f"Loading data from: {file_path}")
            raw = pd.read_csv(file_path)
            
    except Exception as exc:
        raise ValueError(f"Failed to read CSV(s): {exc}") from exc

    if raw.empty:
        raise ValueError("Loaded CSV data is empty.")

    df = _normalize_columns(raw)

    # ── Multi-ticker handling ──────────────────────────────────────────────────
    if "Ticker" in df.columns:
        tickers = df["Ticker"].dropna().unique()
        if len(tickers) == 1:
            ticker = str(tickers[0]).upper()
            single = df[df["Ticker"] == tickers[0]].copy().drop(columns=["Ticker"])
            return _clean_dataframe(single, ticker=ticker)

        result = {}
        errors = []
        for ticker_val in tickers:
            ticker = str(ticker_val).upper()
            
            is_index = ("VNINDEX" in ticker) or ("HNX" in ticker) or ("HAINDEX" in ticker)
            if not (len(ticker) == 3 and ticker.isalnum()) and not is_index:
                continue
                
            sub = df[df["Ticker"] == ticker_val].copy().drop(columns=["Ticker"])
            try:
                result[ticker] = _clean_dataframe(sub, ticker=ticker)
            except ValueError as e:
                errors.append(str(e))
                logger.debug(f"Skipping ticker {ticker}: {e}")

        if not result:
            raise ValueError(f"No valid tickers loaded. Errors:\n" + "\n".join(errors))

        if errors:
            logger.warning(f"{len(errors)} ticker(s) skipped due to validation errors.")

        logger.info(f"Loaded {len(result)} tickers: {sorted(result.keys())}")
        return result

    # ── Single-ticker (no Ticker column) ──────────────────────────────────────
    return _clean_dataframe(df, ticker="SINGLE")
