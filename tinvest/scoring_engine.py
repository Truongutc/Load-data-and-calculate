"""
Module 5 – Scoring Engine
==========================
Aggregates sub-scores from Ichimoku, VSA, and AIC into a total score
and classifies the stock.

Score breakdown
---------------
  Ichimoku : 0 – 3
  VSA      : 0 – 4
  AIC      : 0 – 4
  Total    : 0 – 11

Classification
--------------
  ≥ 9  → STRONG BUY
  7–8  → BUY
  5–6  → WATCH
  < 5  → AVOID
"""

import logging

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
_THRESHOLDS = [
    (9, "STRONG BUY"),
    (7, "BUY"),
    (5, "WATCH"),
    (0, "AVOID"),
]


def calculate_score(
    ichimoku_result: dict,
    vsa_result: dict,
    aic_result: dict,
) -> dict:
    """
    Aggregate sub-scores into a total score and classify the stock.

    Parameters
    ----------
    ichimoku_result : dict  – output of ichimoku_engine.analyze_ichimoku()
    vsa_result      : dict  – output of vsa_engine.analyze_vsa()
    aic_result      : dict  – output of aic_engine.analyze_aic()

    Returns
    -------
    dict:
        {
            "total_score"    : int,
            "classification" : str,
            "breakdown"      : {"ichimoku": int, "vsa": int, "aic": int}
        }
    """
    ichi_score = int(ichimoku_result.get("score", 0))
    vsa_score  = int(vsa_result.get("score", 0))
    aic_score  = int(aic_result.get("score", 0))

    total = ichi_score + vsa_score + aic_score

    classification = "AVOID"
    for threshold, label in _THRESHOLDS:
        if total >= threshold:
            classification = label
            break

    result = {
        "total_score":    total,
        "classification": classification,
        "breakdown": {
            "ichimoku": ichi_score,
            "vsa":      vsa_score,
            "aic":      aic_score,
        },
    }
    logger.debug(f"Score: {result}")
    return result
