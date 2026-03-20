"""
Module 11 – Strict Trade Valuation & Exit Engine (Modular AIC Version 2.0)
=========================================================================
Implements signal-aware price positioning, adaptive S/R, and Risk Scoring.
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

def _get_indicators(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    return {
        "price": float(last['Close']),
        "ma20": float(last['MA20']),
        "ma50": float(last['MA50']),
        "tenkan": float(last['Tenkan']),
        "kijun": float(last['Kijun']),
        "k65": float(last['Kijun65']),
        "span_a": float(last['SpanA']),
        "span_b": float(last['SpanB']),
        "cloud_top": float(max(last['SpanA'], last['SpanB'])),
        "low10": float(df['Low'].iloc[-10:].min()),
        "low20": float(df['Low'].iloc[-20:].min()), # Base Low
        "hh10": float(df['High'].iloc[-10:].max())
    }

def _get_entry_levels(df: pd.DataFrame) -> dict:
    """Scan last 20 bars for signals and their levels."""
    from .advanced_entry import _eval_day, ensure_indicators
    df = ensure_indicators(df.copy())
    levels = {"EARLY": 0.0, "ADD_1": 0.0, "ADD_2": 0.0, "STRONG": 0.0}
    for i in range(1, 21):
        idx = -i
        if abs(idx) > len(df): break
        res = _eval_day(df, idx)
        if res:
            t = res["type"]
            if t in levels and levels[t] == 0:
                levels[t] = float(df['Close'].iloc[idx])
    return levels

def _classify_position(price: float, levels: dict) -> str:
    """Classify where price sits relative to signals."""
    if levels["STRONG"] > 0 and price >= levels["STRONG"]:
        return "Vượt điểm mua MẠNH"
    if levels["ADD_2"] > 0 and price >= levels["ADD_2"]:
        return "Vượt điểm gia tăng 2"
    if levels["ADD_1"] > 0 and price >= levels["ADD_1"]:
        return "Vượt điểm gia tăng 1"
    if levels["EARLY"] > 0:
        if price >= levels["EARLY"] * 1.01:
            return "Vượt điểm mua sớm"
        if price >= levels["EARLY"] * 0.98:
            return "Vùng điểm mua sớm"
        return "Nằm dưới điểm mua sớm"
    return "Chưa có tín hiệu mua"

def _determine_state(p: float, inds: dict) -> str:
    m20, m50 = inds["ma20"], inds["ma50"]
    tk, kj, ct = inds["tenkan"], inds["kijun"], inds["cloud_top"]
    k65 = inds["k65"]
    
    is_strong = (p > m20 > m50) and (p > ct) and (tk > kj) and (p > k65)
    is_uptrend = (p > m20) and not is_strong
    is_sideway = (inds["span_b"] >= p >= inds["span_a"]) or (abs(p - m20) / m20 < 0.02)
    is_downtrend = (p < m20) and (tk < kj)
    
    if is_strong: return "STRONG_UPTREND"
    if is_uptrend: return "UPTREND"
    if is_downtrend: return "DOWNTREND"
    return "SIDEWAY"

def _calculate_sr_adaptive(price: float, inds: dict, levels: dict, pos: str) -> dict:
    # Default Indicator Support
    # Rule: Indicator only valid if Price > Indicator
    def valid_support(val, p): return val if p > val else 0
    
    s_ma20 = valid_support(inds["ma20"], price)
    s_tk = valid_support(inds["tenkan"], price)
    s_kj65 = valid_support(inds["k65"], price)
    
    # S1 (Near): If passed EarlyBuy, S1 = EarlyBuy or Base Low
    if "Vượt điểm" in pos:
        # User requirement: Cutloss at Base Bottom or breaking EarlyBuy
        s1 = max(levels["EARLY"], inds["low10"]) if levels["EARLY"] > 0 else max(s_ma20, s_tk)
    else:
        s1 = max(s_ma20, s_tk, inds["low10"])
        
    if s1 == 0 or s1 > price: s1 = price * 0.95 # Fallback
    
    # S2 (Deep): Base Low or deep indicators
    s2 = min(inds["low20"], inds["ma50"] if inds["ma50"] < s1 else s1 * 0.95)
    if s2 > s1: s2 = s1 * 0.95
    
    # R1 (Target): min(HH10, Price * 1.10)
    r1 = min(inds["hh10"] if inds["hh10"] > price else price * 1.08, price * 1.10)
    if r1 <= price: r1 = price * 1.05 # Ensure R1 > Price
    
    # R2 (Further): Price * 1.15
    r2 = max(price * 1.15, r1 * 1.05)
    
    return {"s1": s1, "s2": s2, "r1": r1, "r2": r2}

def _calculate_buffers(price: float, sr: dict, ma20: float, tenkan: float) -> dict:
    return {
        "break_buy": float(sr["r1"] * 1.01),
        "cutloss_partial": float(sr["s1"] * 0.99),
        "cutloss_full": float(sr["s2"] * 0.97),
        "tp1": float(sr["r1"] * 0.98),
        "tp2": float(sr["r2"] * 0.98),
        "trailing_stop": float(max(ma20, tenkan))
    }

def _calculate_risk_score(inds: dict, sr: dict) -> dict:
    p = inds["price"]
    score = 0
    if p < inds["ma20"]: score += 30
    if inds["tenkan"] < inds["kijun"]: score += 20
    if p < inds["cloud_top"]: score += 20
    if p < inds["k65"]: score += 20
    
    # User's RR logic: Reward = R1 - P, Risk = P - S1
    risk_amt = max(0.01, p - sr["s1"])
    reward_amt = max(0.01, sr["r1"] - p)
    
    risk_pct = round((risk_amt / p) * 100, 2)
    reward_pct = round((reward_amt / p) * 100, 2)
    
    rr = reward_amt / risk_amt
    if rr < 1.0: score += 10
    
    desc = "Low" if score <= 30 else ("Medium" if score <= 60 else "High")
    return {
        "score": score, 
        "desc": desc, 
        "rr": round(rr, 2),
        "risk_pct": risk_pct,
        "reward_pct": reward_pct
    }

def evaluate_stock_valuation(ticker: str, df: pd.DataFrame, entry_info: dict) -> dict:
    if len(df) < 65:
        return {"is_valid": False, "reason": "Dữ liệu quá ngắn (<65 phiên)"}

    # Step 1: Get Basic Indicators
    inds = _get_indicators(df)
    price = inds["price"]
    
    # Step 2: Get Signal History & Price Position
    levels = _get_entry_levels(df)
    pos = _classify_position(price, levels)
    
    # Step 3: Determine State
    state = _determine_state(price, inds)
    
    # Step 4: Calculate Adaptive S/R
    sr = _calculate_sr_adaptive(price, inds, levels, pos)
    
    # Step 5: Calculate Buffers
    buffs = _calculate_buffers(price, sr, inds["ma20"], inds["tenkan"])
    
    # Step 6: Risk Scoring
    risk = _calculate_risk_score(inds, sr)
    
    # Conclusion
    # If there's an ENTRY TYPE today, action should not be NO unless extreme risk
    entry_today = entry_info.get("entry_type") != "NONE"
    
    action = "WAIT"
    if entry_today:
        if risk["score"] > 80:
             action = "NO (Rủi ro cực cao)"
        else:
             action = "YES" if (risk["rr"] >= 1.0 or state == "STRONG_UPTREND") else "WAIT (RR thấp)"
    elif state in ["STRONG_UPTREND", "UPTREND"]:
        action = "YES" if risk["rr"] >= 1.2 else "WAIT (RR thấp)"
    elif state == "DOWNTREND":
        action = "NO"
        
    fomo = price > inds["ma20"] * 1.12

    return {
        "is_valid": True,
        "ticker": ticker,
        "state": state,
        "position": pos,
        "price": price,
        "s1": float(sr["s1"]),
        "s2": float(sr["s2"]),
        "r1": float(sr["r1"]),
        "r2": float(sr["r2"]),
        "break_buy": buffs["break_buy"],
        "cutloss_partial": buffs["cutloss_partial"],
        "cutloss_full": buffs["cutloss_full"],
        "tp1": buffs["tp1"],
        "tp2": buffs["tp2"],
        "trailing_stop": buffs["trailing_stop"],
        "risk_score": risk["score"],
        "risk_desc": risk["desc"],
        "rr_ratio": risk["rr"],
        "risk_pct": risk["risk_pct"],
        "reward_pct": risk["reward_pct"],
        "action": action,
        "fomo_warning": fomo,
        "details": {
            "ma20": inds["ma20"],
            "ma50": inds["ma50"],
            "tenkan": inds["tenkan"],
            "kijun": inds["kijun"],
            "k65": inds["k65"],
            "cloud_top": inds["cloud_top"],
            "levels": levels
        }
    }
