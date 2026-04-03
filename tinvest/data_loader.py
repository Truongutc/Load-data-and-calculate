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
    Enriches an OHLCV DataFrame with ALL technical indicators.
    Ensures SSoT by re-calculating all indicators to prevent data drift.
    """
    if len(df) < 2:
        return df

    out = df.copy().reset_index(drop=True) 

    # ── 1. Moving Averages ─────────────────────────────────────────────────
    for period, name in [(10, 'MA10'), (20, 'MA20'), (50, 'MA50'), (100, 'MA100'), (200, 'MA200')]:
        out[name] = out['Close'].rolling(period).mean()

    # ── 2. ATR14 ───────────────────────────────────────────────────────────
    high_low = out['High'] - out['Low']
    high_prev_close = (out['High'] - out['Close'].shift(1)).abs()
    low_prev_close = (out['Low'] - out['Close'].shift(1)).abs()
    tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
    out['ATR14'] = tr.rolling(14).mean()

    # ── 3. Volume ──────────────────────────────────────────────────────────
    out['AvgVolume20'] = out['Volume'].rolling(20).mean()

    # ── 4. Ichimoku ────────────────────────────────────────────────────────
    for period, name in [(9, 'Tenkan'), (26, 'Kijun'), (65, 'Kijun65'), (52, 'SpanB_raw')]:
        target_name = name if name != 'SpanB_raw' else 'SpanB'
        res = (out['High'].rolling(period).max() + out['Low'].rolling(period).min()) / 2
        if name == 'SpanB_raw':
            res = res.shift(26)
        out[target_name] = res

    out['SpanA'] = ((out['Tenkan'] + out['Kijun']) / 2).shift(26)
    out['Chikou'] = out['Close'].shift(-26)
    out['CloudTop'] = out[['SpanA', 'SpanB']].max(axis=1)
    out['CloudBottom'] = out[['SpanA', 'SpanB']].min(axis=1)

    # ── 5. Heikin Ashi ─────────────────────────────────────────────────────
    # HA is a chain - must compute from start to ensure integrity
    ha_close = (out['Open'] + out['High'] + out['Low'] + out['Close']) / 4
    ha_open = np.zeros(len(out))
    
    ha_open[0] = (out['Open'].iloc[0] + out['Close'].iloc[0]) / 2
    for i in range(1, len(out)):
        ha_open[i] = (ha_open[i-1] + ha_close.iloc[i-1]) / 2
        
    out['HA_Open'] = ha_open
    out['HA_Close'] = ha_close
    out['HA_Color'] = np.where(ha_close > ha_open, 'Green', 'Red')

    # ── 6. RSI (Relative Strength Index) ──────────────────────────────────
    delta = out['Close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # Use Wilder's smoothing/EWM
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    
    rs = avg_gain / (avg_loss + 1e-10)
    out['RSI'] = 100 - (100 / (1 + rs))

    # ── 7. MACD (Moving Average Convergence Divergence) ───────────────────
    ema12 = out['Close'].ewm(span=12, adjust=False).mean()
    ema26 = out['Close'].ewm(span=26, adjust=False).mean()
    out['MACD'] = ema12 - ema26
    out['MACD_Signal'] = out['MACD'].ewm(span=9, adjust=False).mean()
    out['MACD_Hist'] = out['MACD'] - out['MACD_Signal']
    
    # ── 8. ADX (Average Directional Index) ────────────────────────────────
    # Period = 14
    period = 14
    plus_dm = (out['High'] - out['High'].shift(1)).clip(lower=0)
    minus_dm = (out['Low'].shift(1) - out['Low']).clip(lower=0)
    
    # +DM only if > -DM, else 0
    plus_dm = np.where((plus_dm > minus_dm), plus_dm, 0)
    minus_dm = np.where((minus_dm > plus_dm), minus_dm, 0)
    
    tr1 = out['High'] - out['Low']
    tr2 = (out['High'] - out['Close'].shift(1)).abs()
    tr3 = (out['Low'] - out['Close'].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Wilder's Smoothing (RMA)
    tr_smoothed = tr.ewm(com=period-1, adjust=False).mean()
    plus_di = 100 * (pd.Series(plus_dm).ewm(com=period-1, adjust=False).mean() / tr_smoothed)
    minus_di = 100 * (pd.Series(minus_dm).ewm(com=period-1, adjust=False).mean() / tr_smoothed)
    
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    out['ADX'] = dx.ewm(com=period-1, adjust=False).mean()
    out['DI_Plus'] = plus_di
    out['DI_Minus'] = minus_di

    # ── 9. Pivot (Swing) Points (Fractal n=2) ───────────────────────────
    # We find peaks/valleys to identify potential S/R
    highs = out['High'].values
    lows = out['Low'].values
    n = 2
    swing_highs = np.zeros(len(out))
    swing_lows = np.zeros(len(out))
    
    for i in range(n, len(out) - n):
        # Swing High
        if highs[i] == max(highs[i-n:i+n+1]):
            swing_highs[i] = highs[i]
        # Swing Low
        if lows[i] == min(lows[i-n:i+n+1]):
            swing_lows[i] = lows[i]
            
    out['SwingHigh'] = swing_highs
    out['SwingLow'] = swing_lows

    # ── 10. VSA Helpers ─────────────────────────────────────────────────────
    out['Spread'] = out['High'] - out['Low']
    out['Avg_Spread_20'] = out['Spread'].rolling(20).mean()
    
    out['Stopping_Vol'] = (out['Volume'] > 1.5 * out['AvgVolume20']) & \
                          (out['Spread'] > out['Avg_Spread_20']) & \
                          (out['Close'] > out['Low'] + 0.3 * out['Spread'])
    
    out['No_Supply'] = (out['Volume'] < 0.7 * out['AvgVolume20']) & \
                       (out['Spread'] < out['Avg_Spread_20']) & \
                       (out['Close'] < out['Open'])
    
    out['Test_Supply'] = (out['Volume'] < out['AvgVolume20']) & \
                         (out['Spread'] < out['Avg_Spread_20'] * 0.8) & \
                         (out['Close'] > out['Low'] + 0.4 * out['Spread'])

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
