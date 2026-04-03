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
        "ma10": float(last.get('MA10', df['Close'].rolling(10).mean().iloc[-1])),
        "ma20": float(last['MA20']),
        "ma50": float(last['MA50']),
        "tenkan": float(last['Tenkan']),
        "kijun": float(last['Kijun']),
        "k65": float(last['Kijun65']),
        "span_a": float(last['SpanA']),
        "span_b": float(last['SpanB']),
        "cloud_top": float(max(last['SpanA'], last['SpanB'])),
        "cloud_bottom": float(min(last['SpanA'], last['SpanB'])),
        "rsi": float(last.get('RSI', 50)),
        "macd": float(last.get('MACD', 0)),
        "macd_hist": float(last.get('MACD_Hist', 0)),
        "adx": float(last.get('ADX', 0)),
        "di_plus": float(last.get('DI_Plus', 0)),
        "di_minus": float(last.get('DI_Minus', 0))
    }

def _find_swing_points(df: pd.DataFrame, n: int = 2) -> dict:
    """Extract confirmed Swing Highs and Swing Lows from the enriched dataframe."""
    sh = df[df['SwingHigh'] > 0]['SwingHigh'].tolist()
    sl = df[df['SwingLow'] > 0]['SwingLow'].tolist()
    return {"peaks": sh, "valleys": sl}

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

def _determine_state(p: float, inds: dict, entry_type: str) -> str:
    """Determine UI friendly state name."""
    if entry_type == "STRONG": return "TRẠNG THÁI D: MUA MẠNH"
    if entry_type == "ADD_2": return "TRẠNG THÁI C: GIA TĂNG 2"
    if entry_type == "ADD_1": return "TRẠNG THÁI B: GIA TĂNG 1"
    if entry_type == "EARLY": return "TRẠNG THÁI A: MUA SỚM"
    return "TRẠNG THÁI 0: THEO DÕI"

def _calculate_exits_and_sr(df: pd.DataFrame, inds: dict, entry_info: dict) -> dict:
    p = inds["price"]
    entry_type = entry_info.get("entry_type", "NONE")
    
    # Get Pivot Points
    swings = _find_swing_points(df)
    peaks = swings["peaks"]
    valleys = swings["valleys"]
    
    # Defaults
    s1, s2, r1, r2, r3 = 0.0, 0.0, 0.0, 0.0, 0.0
    tp, sl, ts = 0.0, 0.0, 0.0
    
    # Helper to get N-th peak/valley back from price
    v_low_vals = sorted([v for v in valleys if v < p], reverse=True)
    v_high_peaks = sorted([v for v in peaks if v > p])

    # --- STATE 0: NONE ---
    if entry_type == "NONE":
        s1 = v_low_vals[0] if v_low_vals else p * 0.95
        r1 = v_high_peaks[0] if v_high_peaks else p * 1.05
        tp = r1
        sl = s1

    # --- STATE A: EARLY ---
    elif entry_type == "EARLY":
        s1 = v_low_vals[0] if v_low_vals else p * 0.95
        r1 = v_high_peaks[0] if v_high_peaks else p * 1.10
        tp = r1
        sl = s1

    # --- STATE B: ADD_1 ---
    elif entry_type == "ADD_1":
        r1 = v_high_peaks[0] if v_high_peaks else p * 1.10
        r2 = v_high_peaks[1] if len(v_high_peaks) >= 2 else r1 * 1.07
        s1 = max(inds["ma20"], inds["kijun"])
        tp = r2
        sl = s1

    # --- STATE C: ADD_2 ---
    elif entry_type == "ADD_2":
        r1 = v_high_peaks[0] if v_high_peaks else p * 1.10
        r2 = v_high_peaks[1] if len(v_high_peaks) >= 2 else r1 * 1.07
        r3 = v_high_peaks[2] if len(v_high_peaks) >= 3 else r2 * 1.10
        s1 = max(inds["kijun"], inds["span_a"])
        tp = r3
        sl = s1

    # --- STATE D: STRONG ---
    elif entry_type == "STRONG":
        s1 = inds["ma10"]
        # TP: Athena or Fibo 127.2%
        r1 = v_high_peaks[0] if v_high_peaks else p * 1.127
        tp = r1
        sl = s1

    # Fallbacks and TP/SL adjustments
    if tp <= p: tp = p * 1.10
    if sl >= p: sl = p * 0.95
    ts = s1 # ADX Strong Trend uses S1/MA10 as trailing stop
    
    return {
        "s1": float(s1), "s2": float(s1 * 0.95), "r1": float(r1), "r2": float(r2),
        "tp1": float(tp), "tp2": float(r2 if r2 > 0 else tp * 1.10),
        "trailing_stop": float(ts),
        "cutloss_partial": float(sl),
        "cutloss_full": float(sl * 0.98),
        "break_buy": float(r1 * 1.01) if r1 > 0 else float(p * 1.05)
    }

def _evaluate_technical_health(df: pd.DataFrame, inds: dict) -> dict:
    """
    Diagnostic tool to evaluate stock health using ADX, RSI, and MACD.
    Does not change trading state, only provides health insights.
    """
    # 1. ADX Analysis (Trend Strength)
    adx = inds["adx"]
    p_adx = df['ADX'].iloc[-2] if len(df) > 1 else adx
    adx_rising = adx > p_adx
    
    adx_desc = "Xu hướng yếu (Sideway)"
    if adx > 25: adx_desc = "Xu hướng mạnh"
    if adx > 40: adx_desc = "Xu hướng cực mạnh (Quá mua/Bán)"
    adx_status = f"{adx_desc} [{'Tăng' if adx_rising else 'Giảm'}]"
    
    # 2. RSI Analysis (Momentum)
    rsi = inds["rsi"]
    rsi_desc = "Trung tính"
    if rsi > 60: rsi_desc = "Xung lực tăng mạnh"
    elif rsi > 50: rsi_desc = "Xung lực tăng nhẹ"
    elif rsi < 30: rsi_desc = "Quá bán (Dưới 30)"
    elif rsi < 40: rsi_desc = "Xung lực yếu"
    rsi_status = f"{rsi_desc} ({rsi:.1f})"
    
    # 3. MACD Analysis (Direction)
    hist = inds["macd_hist"]
    p_hist = df['MACD_Hist'].iloc[-2] if len(df) > 1 else hist
    hist_rising = hist > p_hist
    macd_status = "Tích cực (Histogram tăng)" if hist_rising else "Tiêu cực (Histogram giảm)"
    if inds["macd"] > 0 and inds["macd_hist"] > 0:
        macd_status = "Đà tăng mạnh (MACD > 0 & Hist > 0)"

    # 4. Combined Technical Health
    score = 0
    if adx > 20 and adx_rising: score += 1
    if rsi > 50: score += 1
    if hist_rising: score += 1
    if inds["macd"] > 0: score += 1
    
    health_label = "YẾU"
    if score >= 4: health_label = "RẤT KHỎE"
    elif score >= 3: health_label = "KHỎE"
    elif score >= 2: health_label = "CẢI THIỆN"
    
    return {
        "adx_label": adx_status,
        "rsi_label": rsi_status,
        "macd_label": macd_status,
        "health_rating": health_label,
        "health_score": score
    }

def _calculate_risk_score(df: pd.DataFrame, inds: dict, exits: dict) -> dict:
    p = inds["price"]
    score = 0
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    prev_macd_hist = float(prev.get('MACD_Hist', 0))
    
    score_trend = 0
    if p < inds["ma20"]: score_trend += 8
    if inds["tenkan"] < inds["kijun"]: score_trend += 8
    if p < inds["cloud_bottom"]: score_trend += 15
    elif p <= inds["cloud_top"]: score_trend += 10
    score += min(30, score_trend)
    
    score_structure = 0
    if p < inds["kijun"]: score_structure += 10
    if p < inds["k65"]: score_structure += 20
    score += min(35, score_structure)
    
    score_vsa = 0
    vol_dist = (last['Close'] < prev['Close']) and (last['Volume'] > prev['Volume'])
    if vol_dist: score_vsa += 15
    avg_vol20 = float(df['Volume'].iloc[-20:].mean()) if len(df) >= 20 else float(df['Volume'].mean())
    vol_weak = last['Volume'] < avg_vol20
    if vol_weak: score_vsa += 10
    score += min(25, score_vsa)
    
    # ---- TRAP & BOUNCE DETECTION ----
    bull_trap = (inds["rsi"] > 70) and (last['Volume'] < avg_vol20 or inds["macd_hist"] < prev_macd_hist)
    bottom_bounce = (inds["rsi"] < 30) and (last['Volume'] < 0.8 * avg_vol20) and (inds["macd_hist"] > prev_macd_hist)

    score = int(max(0, min(100, score)))
    risk_amt = max(0.01, p - exits["cutloss_partial"])
    reward_amt = max(0.01, exits["tp1"] - p)
    rr = reward_amt / risk_amt
    
    desc = "LOW"
    if score > 75 or bull_trap: desc = "EXTREME"
    elif score > 50: desc = "HIGH"
    elif score > 25: desc = "MEDIUM"
    
    return {
        "score": score, "desc": desc, "rr": round(rr, 2),
        "risk_pct": round((risk_amt / p) * 100, 2),
        "reward_pct": round((reward_amt / p) * 100, 2),
        "vol_dist": vol_dist, "vol_weak": vol_weak,
        "bull_trap": bull_trap, "bottom_bounce": bottom_bounce
    }

def evaluate_stock_valuation(ticker: str, df: pd.DataFrame, entry_info: dict) -> dict:
    if len(df) < 2: return {"is_valid": False, "reason": "Dữ liệu quá ngắn"}
    
    inds = _get_indicators(df)
    price = inds["price"]
    entry_type = entry_info.get("entry_type", "NONE")
    
    levels = _get_entry_levels(df)
    pos = _classify_position(price, levels)
    state = _determine_state(price, inds, entry_type)
    
    exits = _calculate_exits_and_sr(df, inds, entry_info)
    risk = _calculate_risk_score(df, inds, exits)
    health = _evaluate_technical_health(df, inds)
    
    # Conclusion logic: Combine State + Health + MAs
    ma_ok = price > inds["ma20"]
    cloud_ok = price > inds["cloud_top"]
    
    entry_today = entry_type != "NONE"
    action = "WAIT"
    
    if risk["score"] > 75 or risk["vol_dist"]:
        action = "NO TRADE"
    elif health["health_score"] >= 3 and ma_ok and cloud_ok:
        action = "YES (Ưu tiên tham gia)"
    elif (entry_today or health["health_score"] >= 2) and risk["rr"] >= 1.2:
        action = "YES (Có thể cân nhắc)"
    else:
        action = "WAIT (Chờ xác nhận)"
        
    fomo = price > inds["ma20"] * 1.12

    return {
        "is_valid": True, "ticker": ticker, "state": state, "position": pos,
        "price": price, "s1": exits["s1"], "s2": exits["s2"],
        "r1": exits["r1"], "r2": exits["r2"], "break_buy": exits["break_buy"],
        "cutloss_partial": exits["cutloss_partial"], "cutloss_full": exits["cutloss_full"],
        "tp1": exits["tp1"], "tp2": exits["tp2"], "trailing_stop": exits["trailing_stop"],
        "risk_score": risk["score"], "risk_desc": risk["desc"],
        "rr_ratio": risk["rr"], "risk_pct": risk["risk_pct"],
        "reward_pct": risk["reward_pct"], "action": action, "fomo_warning": fomo or risk["bull_trap"],
        "bottom_bounce": risk["bottom_bounce"],
        "tech_health": health,
        "details": {"ma20": inds["ma20"], "ma50": inds["ma50"], "tenkan": inds["tenkan"],
                    "kijun": inds["kijun"], "k65": inds["k65"], "cloud_top": inds["cloud_top"],
                    "rsi": inds["rsi"], "levels": levels}
    }
