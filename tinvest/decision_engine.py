"""
Module 6 – Decision Engine (Risk & Opportunity)
================================================
Generates human-readable opportunity and risk signals based on the
combined output of Ichimoku, VSA, and AIC engines.

Output dict
-----------
{
    "opportunity" : [str, ...],
    "risk"        : [str, ...]
}
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)


def analyze_decision(
    df: pd.DataFrame,
    ichimoku_result: dict,
    vsa_result: dict,
    aic_result: dict,
) -> dict:
    """
    Evaluate opportunity and risk signals.

    Parameters
    ----------
    df              : pd.DataFrame  – clean OHLCV data
    ichimoku_result : dict          – output of ichimoku_engine
    vsa_result      : dict          – output of vsa_engine
    aic_result      : dict          – output of aic_engine

    Returns
    -------
    dict  {"opportunity": [...], "risk": [...]}
    """
    opportunity: list[str] = []
    risk: list[str]        = []

    last  = df.iloc[-1]
    close = last["Close"]

    # ── Opportunity signals ───────────────────────────────────────────────────
    # 1. Breakout present
    if aic_result.get("setup") == "A":
        bo_level = aic_result.get("breakout_level")
        opportunity.append(
            f"✅ Breakout xác nhận: Giá đóng cửa {close:.2f} vượt ngưỡng kháng cự {bo_level:.2f}"
        )

    # 2. Pullback into breakout zone (low-risk entry)
    if aic_result.get("setup") == "B":
        bo_level = aic_result.get("breakout_level")
        opportunity.append(
            f"✅ Pullback về vùng breakout {bo_level:.2f} – cơ hội mua giá tốt"
        )

    # 3. Early accumulation
    if aic_result.get("setup") == "C":
        opportunity.append("✅ Dấu hiệu tích lũy sớm (Stopping Volume + Hammer)")

    # 4. Bullish money flow (VSA)
    vsa_signals = [s["type"] for s in vsa_result.get("signals", [])]
    if "stopping_volume" in vsa_signals:
        opportunity.append("✅ Stopping Volume: Dòng tiền lớn đang hấp thụ cung")
    if "no_supply" in vsa_signals:
        opportunity.append("✅ No Supply: Không còn áp lực bán, cung cạn")
    if "push_up" in vsa_signals:
        opportunity.append("✅ Push Up: Lực mua chiếm ưu thế rõ ràng")

    # 5. Trend confirmation
    if ichimoku_result.get("trend") == "UP":
        opportunity.append("✅ Xu hướng tăng: Giá trên mây Ichimoku")
    if ichimoku_result.get("cloud_color") == "green":
        opportunity.append("✅ Mây xanh phía trước: Xu hướng tăng tiếp tục")
    if ichimoku_result.get("tenkan_kijun_cross") == "bullish":
        opportunity.append("✅ Tenkan cắt Kijun từ dưới lên: Tín hiệu mua mạnh")

    # ── Risk signals ──────────────────────────────────────────────────────────
    # 1. Near 20-bar high (overbought zone)
    high_20 = df["High"].iloc[-20:].max() if len(df) >= 20 else df["High"].max()
    pct_from_high = (high_20 - close) / (high_20 + 1e-10)
    if pct_from_high < 0.03:
        risk.append(f"⚠️ Giá gần đỉnh 20 phiên ({high_20:.2f}) – rủi ro mua đỉnh")

    # 2. Bearish VSA signals
    if "upthrust" in vsa_signals:
        risk.append("⚠️ Upthrust: Giá bị đẩy lên rồi bị bán mạnh – dấu hiệu phân phối")
    if "no_demand" in vsa_signals:
        risk.append("⚠️ No Demand: Cú tăng thiếu lực cầu – xu hướng yếu")

    # 3. Downtrend
    if ichimoku_result.get("trend") == "DOWN":
        risk.append("⚠️ Xu hướng giảm: Giá dưới mây Ichimoku – không nên mua")
    if ichimoku_result.get("trend") == "SIDEWAY":
        risk.append("⚠️ Giá trong mây (SIDEWAY): Xu hướng chưa rõ, rủi ro cao")

    # 4. Kijun sloping down
    if ichimoku_result.get("kijun_slope") == "down":
        risk.append("⚠️ Kijun nghiêng xuống: Momentum giảm")

    # 5. Bearish TK cross
    if ichimoku_result.get("tenkan_kijun_cross") == "bearish":
        risk.append("⚠️ Tenkan cắt Kijun từ trên xuống: Tín hiệu bán")

    # 6. No valid AIC setup
    if aic_result.get("setup") == "NONE":
        risk.append("⚠️ Không có điểm vào AIC rõ ràng – chờ thêm tín hiệu")

    result = {"opportunity": opportunity, "risk": risk}
    logger.debug(f"Decision: {len(opportunity)} opportunities, {len(risk)} risks")
    return result
