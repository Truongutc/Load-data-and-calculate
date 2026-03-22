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

def _get_nearest_peak(df, idx=None, lookback=10):
    if idx is None: idx = -1
    if len(df) < lookback: return float(df['High'].max())
    return float(df['High'].iloc[-lookback:].max())

def _get_nearest_valley(df, idx=None, lookback=10):
    if idx is None: idx = -1
    if len(df) < lookback: return float(df['Low'].min())
    return float(df['Low'].iloc[-lookback:].min())

def _get_second_nearest_peak(df, idx=None, lookback1=10, lookback2=20):
    if idx is None: idx = -1
    if len(df) < lookback2: return _get_nearest_peak(df, idx, lookback1)
    return float(df['High'].iloc[-lookback2:-lookback1].max())

def _calculate_exits_and_sr(df, inds: dict, entry_info: dict) -> dict:
    p = inds["price"]
    entry_type = entry_info.get("entry_type", "NONE")
    source = entry_info.get("details", {}).get("source", "UNKNOWN")
    
    last = df.iloc[-1]
    
    nearest_peak = _get_nearest_peak(df, -1, 10)
    second_peak = _get_second_nearest_peak(df, -1, 10, 20)
    if second_peak < p: second_peak = nearest_peak * 1.05
    nearest_valley = _get_nearest_valley(df, -1, 10)
    short_term_valley = _get_nearest_valley(df, -1, 5)
    
    ma10 = inds['ma10']
    ma20 = inds['ma20']
    ma50 = inds['ma50']
    tk = inds['tenkan']
    kj = inds['kijun']
    k65 = inds['k65']
    cloud_top = inds['cloud_top']
    cloud_bottom = min(inds['span_a'], inds['span_b'])
    price_above_cloud = p > cloud_top
    price_below_cloud = p < cloud_bottom
    
    # Defaults
    r1, r2, s1, s2 = p * 1.05, p * 1.10, p * 0.95, p * 0.90
    tp, ts, sl, sell_all = p * 1.05, p * 0.95, p * 0.95, p * 0.90
    
    if entry_type == "EARLY":
        if source == "MA":
            r1 = min(p * 1.15, nearest_peak) if p * 1.15 < nearest_peak or nearest_peak < p else nearest_peak
            r2 = max(p * 1.15, nearest_peak)
            s1 = max(nearest_valley, ma10)
            s2 = min(nearest_valley, ma10)
            tp = r1
            ts = ma10
            sl = max(p * 0.90, ma10, nearest_valley)
            sell_all = min(p * 0.90, ma10, nearest_valley)
            
        elif source == "ICHIMOKU":
            if price_below_cloud:
                r1 = min(kj, k65)
                r2 = max(kj, k65)
                s1 = max(tk, nearest_valley)
                s2 = min(tk, nearest_valley)
                tp = r1
                ts = min(r1 * 0.97, p * 1.10)
                sl = max(tk, nearest_valley, p * 0.90)
                sell_all = short_term_valley * 0.98
            else: # trên mây
                r1 = min(kj, nearest_peak)
                r2 = max(kj, nearest_peak)
                s1 = max(k65, tk)
                s2 = min(k65, tk)
                tp = r1
                ts = min(r1 * 0.97, p * 1.10)
                sl = s1 * 0.97
                sell_all = cloud_top if p > cloud_top else cloud_bottom
        else: # VSA or fallback
            r1 = nearest_peak
            r2 = second_peak
            s1 = ma20
            s2 = ma50
            tp = r1
            ts = max(ma20, p * 0.95)
            sl = nearest_valley
            sell_all = nearest_valley * 0.95

    elif entry_type in ["ADD_1", "ADD_2"]:
        if source == "MA_PULLBACK":
            r1 = nearest_peak
            r2 = second_peak
            s1 = ma20
            s2 = ma50
            tp = r1
            ts = min(p * 1.10, r1)
            sl = ma20 * 0.97
            sell_all = ma50 * 0.97
        elif source == "MA_CROSS" or source == "MA":
            r1 = nearest_peak
            r2 = second_peak
            s1 = ma20
            s2 = ma50
            tp = r1
            ts = min(p * 1.10, r1)
            if p < kj: ts = min(ts, kj)
            sl = ma20 * 0.97
            sell_all = ma50 * 0.97
        elif source == "ICHIMOKU":
            if price_below_cloud:
                r1 = min(k65, cloud_top, nearest_peak)
                r2 = min(nearest_peak, cloud_top)
                s1 = tk
                s2 = kj
                tp = r1
                ts = min(p * 1.10, r1)
                sl = max(s1 * 0.97, p * 0.90)
                sell_all = kj * 0.95
            else: # Trên mây
                r1 = nearest_peak
                r2 = second_peak
                s1 = max(k65 if k65 < p else 0, tk)
                s2_candidates = [v for v in (k65 if k65 < p else float('inf'), ma20, kj) if v > 0]
                s2 = min(s2_candidates) if s2_candidates else min(ma20, kj)
                tp = r1
                ts = min(r1 * 0.97, p * 1.10)
                sl = s1 * 0.97
                sell_all = cloud_top if p > cloud_top else cloud_bottom
        else:
            r1 = nearest_peak
            r2 = second_peak
            s1 = ma20
            s2 = ma50
            tp = r1
            ts = ma20
            sl = ma20 * 0.97
            sell_all = ma50 * 0.97

    elif entry_type == "STRONG":
        if source == "MA":
            r1 = nearest_peak
            r2 = second_peak
            s1 = ma10
            s2 = ma20
            tp = max(p * 1.15, r1)
            ts = min(p * 1.15, r1)
            sl = min(s1 * 0.95, p * 0.90)
            sell_all = s2 * 0.97
        elif source == "ICHIMOKU":
            r1 = nearest_peak
            r2 = second_peak
            s1 = max(k65 if k65 < p else 0, tk)
            s2_candidates = [val for val in (k65 if k65 < p else float('inf'), ma20, kj) if val > 0]
            s2 = min(s2_candidates) if s2_candidates else min(ma20, kj)
            tp = r1
            ts = min(r1 * 0.97, p * 1.10)
            sl = s1 * 0.97
            sell_all = cloud_top if p > cloud_top else cloud_bottom
        else:
            r1 = nearest_peak
            r2 = second_peak
            s1 = ma10
            s2 = ma20
            tp = r1
            ts = ma10
            sl = ma10 * 0.95
            sell_all = ma20 * 0.95
    else: # NONE hoặc không có tín hiệu
        r1 = nearest_peak
        r2 = second_peak
        s1 = max(ma20, tk)
        s2 = ma50
        tp = r1
        ts = ma20
        sl = s1 * 0.95
        sell_all = s2 * 0.95

    # Safe bounds
    if r1 <= p: r1 = p * 1.05
    if r2 <= r1: r2 = r1 * 1.05
    if tp <= p: tp = r1
    if sl >= p: sl = p * 0.95
    if sell_all >= sl: sell_all = sl * 0.98
    
    return {
        "s1": float(s1), "s2": float(s2), "r1": float(r1), "r2": float(r2),
        "tp1": float(tp), "tp2": float(r2 * 0.98),
        "trailing_stop": float(ts),
        "cutloss_partial": float(sl),
        "cutloss_full": float(sell_all),
        "break_buy": float(r1 * 1.01)
    }

def _calculate_risk_score(df: pd.DataFrame, inds: dict, exits: dict) -> dict:
    p = inds["price"]
    score = 0
    
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    
    # 1. TREND STATE (Đo độ yếu xu hướng, Max 30)
    score_trend = 0
    if p < inds["ma20"]: score_trend += 8
    if inds["tenkan"] < inds["kijun"]: score_trend += 8
    
    cloud_bottom = min(inds["span_a"], inds["span_b"])
    if p < cloud_bottom:
        score_trend += 15
    elif p <= inds["cloud_top"]:  # Trong mây
        score_trend += 10
        
    score += min(30, score_trend)
    
    # 2. STRUCTURE (Xương sống hệ thống, Max 35)
    score_structure = 0
    if p < inds["kijun"]: score_structure += 10
    if p < inds["k65"]: score_structure += 20
    
    swing_low = float(df['Low'].iloc[-50:-1].min()) if len(df) >= 50 else float(df['Low'][:-1].min())
    if p < swing_low:
        score_structure += 15
        
    score += min(35, score_structure)
    
    # 3. VOLUME / DÒNG TIỀN (Max 25)
    score_vsa = 0
    
    vol_dist = (last['Close'] < prev['Close']) and (last['Volume'] > prev['Volume'])
    if vol_dist:
        score_vsa += 15
    elif (last['Close'] > prev['Close']) and (last['Volume'] < prev['Volume']):
        score_vsa += 10
        
    avg_vol20 = float(df['Volume'].iloc[-20:].mean()) if len(df) >= 20 else float(df['Volume'].mean())
    vol_weak = last['Volume'] < avg_vol20
    prev_vol_weak = prev['Volume'] < (df['Volume'].iloc[-21:-1].mean() if len(df) >= 21 else avg_vol20)
    
    if vol_weak and prev_vol_weak:
        score_vsa += 5
        
    score += min(25, score_vsa)
    
    # 4. CONTEXT (Max 10)
    score_context = 0
    p_ma50 = float(df['MA50'].iloc[-2]) if len(df) >= 2 and 'MA50' in df.columns else inds["ma50"]
    if inds["ma50"] < p_ma50: # Ngược xu hướng lớn (MA50 dốc xuống)
        score_context += 10
        
    near_res = (p >= exits["r1"] * 0.98) or (inds["cloud_top"] * 0.98 <= p <= inds["cloud_top"])
    if near_res:
        score_context += 5
        
    near_sup = (inds["k65"] * 1.02 >= p >= inds["k65"]) or (swing_low * 1.02 >= p >= swing_low)
    if near_sup:
        score_context -= 5
        
    score += min(10, max(-10, score_context))
    
    # 8. KILL SWITCH
    if p < inds["k65"] and vol_dist:
        score = max(score, 90)
    
    # Chuẩn hoá tổng điểm 0-100
    score = int(max(0, min(100, score)))
    
    # Tách bóc R/R riêng biệt (Không cộng vào risk score)
    risk_amt = max(0.01, p - exits["cutloss_partial"])
    reward_amt = max(0.01, exits["tp1"] - p)
    
    risk_pct = round((risk_amt / p) * 100, 2)
    reward_pct = round((reward_amt / p) * 100, 2)
    rr = reward_amt / risk_amt
    
    # Phân loại rủi ro chuẩn Trade
    if score <= 25: desc = "LOW"
    elif score <= 50: desc = "MEDIUM"
    elif score <= 75: desc = "HIGH"
    else: desc = "EXTREME"
    
    in_kumo = cloud_bottom <= p <= inds["cloud_top"]
    
    return {
        "score": score, 
        "desc": desc, 
        "rr": round(rr, 2),
        "risk_pct": risk_pct,
        "reward_pct": reward_pct,
        "vol_dist": vol_dist,
        "vol_weak": vol_weak,
        "in_kumo": in_kumo
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
    
    # Step 4 & 5: Calculate Exits and S/R
    exits = _calculate_exits_and_sr(df, inds, entry_info)
    
    # Step 6: Risk Scoring
    risk = _calculate_risk_score(df, inds, exits)
    
    # Conclusion
    entry_today = entry_info.get("entry_type") != "NONE"
    
    action = "WAIT"
    p_kj = price >= inds["kijun"]
    
    # 7. ACTION ENGINE
    r_score = risk["score"]
    
    if r_score > 75 or price < inds["k65"] or risk["vol_dist"]:
        action = "NO TRADE"
    elif r_score <= 50:
        if risk["vol_weak"] or risk["in_kumo"]:
            action = "WAIT (Vol yếu / Giá trong mây)"
        elif entry_today and p_kj and risk["rr"] >= 1.2:
            action = "YES"
        elif not entry_today and state in ["STRONG_UPTREND", "UPTREND"] and p_kj and risk["rr"] >= 1.2:
            action = "YES (Breakout / Tiếp diễn)"
        else:
            action = "WAIT (Chưa Setup / RR Thấp / Dưới Kijun)"
    elif r_score <= 75:
        if entry_today and risk["rr"] >= 1.5:
            action = "YES (Setup nén / Tỷ trọng nhỏ)"
        else:
            action = "WAIT (Rủi ro cao)"
            
    fomo = price > inds["ma20"] * 1.12

    return {
        "is_valid": True,
        "ticker": ticker,
        "state": state,
        "position": pos,
        "price": price,
        "s1": exits["s1"],
        "s2": exits["s2"],
        "r1": exits["r1"],
        "r2": exits["r2"],
        "break_buy": exits["break_buy"],
        "cutloss_partial": exits["cutloss_partial"],
        "cutloss_full": exits["cutloss_full"],
        "tp1": exits["tp1"],
        "tp2": exits["tp2"],
        "trailing_stop": exits["trailing_stop"],
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
