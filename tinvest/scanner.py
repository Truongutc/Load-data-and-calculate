"""
Module 7 – Stock Scanner
========================
Scans a dictionary of tickers (output of data_loader for multi-ticker CSV)
through the full TINVEST pipeline and returns a filtered, ranked DataFrame.

Columns
-------
Ticker | Price | Trend | MoneyFlow | Trigger | Score | Classification | Action

Filter: Only tickers with total Score >= 8 are included.
"""

import logging
import pandas as pd

from .ichimoku_engine import analyze_ichimoku
from .vsa_engine       import analyze_vsa
from .aic_engine       import analyze_aic
from .scoring_engine   import calculate_score
from .decision_engine  import analyze_decision

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 8


def _action_label(classification: str, aic_setup: str) -> str:
    """Convert classification + setup into a short action string."""
    if classification == "STRONG BUY":
        return f"MUA MẠNH ({aic_setup})" if aic_setup != "NONE" else "MUA MẠNH"
    if classification == "BUY":
        return f"MUA ({aic_setup})" if aic_setup != "NONE" else "MUA"
    if classification == "WATCH":
        return "THEO DÕI"
    return "TRÁNH"


def scan_stocks(data_dict: "dict[str, pd.DataFrame]", min_vol: int = 0) -> pd.DataFrame:
    """
    Scan all tickers through the full TINVEST pipeline.

    Parameters
    ----------
    data_dict : dict[str, pd.DataFrame]
        Dict mapping ticker symbols to clean OHLCV DataFrames.
        Typically the output of data_loader.load_data() for a multi-ticker CSV.

    Returns
    -------
    pd.DataFrame
        Filtered and sorted DataFrame (Score >= SCORE_THRESHOLD).
        Columns: Ticker, Price, Trend, MoneyFlow, Trigger, Score, Classification, Action
    """
    if isinstance(data_dict, pd.DataFrame):
        raise TypeError(
            "scan_stocks expects a dict of DataFrames (multi-ticker). "
            "For a single ticker, use analyze_stock() instead."
        )

    rows = []
    total = len(data_dict)
    logger.info(f"Scanning {total} tickers ...")

    for i, (ticker, df) in enumerate(data_dict.items(), 1):
        try:
            # Lọc thanh khoản: Mặc định min_vol = 0 (Không lọc)
            avg_vol_20 = df["Volume"].tail(20).mean() if len(df) >= 20 else df["Volume"].mean()
            if avg_vol_20 < min_vol:
                logger.debug(f"[{ticker}] Skipped due to low volume ({avg_vol_20:,.0f} < {min_vol})")
                continue

            ichi   = analyze_ichimoku(df)
            vsa    = analyze_vsa(df)
            aic    = analyze_aic(df)
            score  = calculate_score(ichi, vsa, aic)
            dec    = analyze_decision(df, ichi, vsa, aic)

            last_close = float(df["Close"].iloc[-1])

            rows.append({
                "Ticker":         ticker,
                "Price":          round(last_close, 2),
                "Trend":          ichi["trend"],
                "MoneyFlow":      vsa["dominant"].capitalize(),
                "Trigger":        aic["setup"],
                "Score":          score["total_score"],
                "Classification": score["classification"],
                "Action":         _action_label(score["classification"], aic["setup"]),
                # Hidden columns for debugging
                "_ichi_score":    ichi["score"],
                "_vsa_score":     vsa["score"],
                "_aic_score":     aic["score"],
                "_opps":          len(dec["opportunity"]),
                "_risks":         len(dec["risk"]),
            })

            logger.info(f"[{i}/{total}] {ticker}: Score={score['total_score']} {score['classification']}")

        except Exception as exc:
            logger.warning(f"[{ticker}] Skipped due to error: {exc}")

    if not rows:
        logger.warning("No tickers passed analysis.")
        return pd.DataFrame()

    result_df = pd.DataFrame(rows)

    # Filter by score threshold
    filtered = result_df[result_df["Score"] >= SCORE_THRESHOLD].copy()

    # Sort by score descending
    filtered = filtered.sort_values("Score", ascending=False).reset_index(drop=True)

    # Public columns only
    public_cols = ["Ticker", "Price", "Trend", "MoneyFlow", "Trigger", "Score", "Classification", "Action"]
    logger.info(f"Scan complete: {len(filtered)}/{total} tickers passed Score >= {SCORE_THRESHOLD}")

    return filtered[public_cols]
