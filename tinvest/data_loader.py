"""
Module 1 – Data Loader
======================
Reads OHLCV CSV files, normalizes columns, and returns clean DataFrames.
Supports single-ticker and multi-ticker CSV files.
"""

import logging
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)

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

MIN_ROWS = 25


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
        # Convert to string first to handle YYYYMMDD integers
        df["Date"] = pd.to_datetime(df["Date"].astype(str))
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
            
            # Chỉ lấy các mã cổ phiếu cơ sở có đúng 3 chữ cái
            if len(ticker) != 3 or not ticker.isalpha():
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
