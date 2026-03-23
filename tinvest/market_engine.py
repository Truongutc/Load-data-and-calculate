"""
Module 8 – Market Regime Engine
===============================
Analyzes Index data (VNINDEX, HNXINDEX) to evaluate CANSLIM Market conditions:
- Distribution Days
- Rally Attempts (RA)
- Follow-Through Days (FTD)
- Mini Trends (Sideway vs Correction)

Returns the current Market Regime and safety scores.
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

def analyze_market_index(df_index: pd.DataFrame) -> dict:
    """
    Quét dữ liệu VNINDEX để xác định trạng thái thị trường chung.
    """
    if df_index is None or df_index.empty or len(df_index) < 50:
        return {
            "regime": "UNKNOWN",
            "ftd_active": False,
            "ra_day": 0,
            "distribution_count": 0,
            "distribution_dates": [],
            "action": "STANDBY"
        }

    # Tính đường viền kỹ thuật (MA50)
    df = df_index.copy()
    df['MA50'] = df['Close'].rolling(50).mean()

    regime = "CORRECTION"
    ra_day = 0
    ra_low = float('inf')
    ftd_active = False
    dist_days = []  # List dicts: {'index': i, 'close': close_val, 'date': datetime}

    for i in range(1, len(df)):
        c = float(df['Close'].iloc[i])
        o = float(df['Open'].iloc[i])
        h = float(df['High'].iloc[i])
        l = float(df['Low'].iloc[i])
        v = float(df['Volume'].iloc[i])
        
        pc = float(df['Close'].iloc[i-1])
        pv = float(df['Volume'].iloc[i-1])
        
        ma50 = float(df['MA50'].iloc[i]) if not pd.isna(df['MA50'].iloc[i]) else c
        
        pct_change = (c - pc) / pc
        
        # 1. CLEAN UP DISTRIBUTION DAYS
        # Theo CANSLIM: Khởi tạo lại chu kỳ 25 phiên hoặc nếu giá vượt 5% so với đỉnh ngày phân phối đó
        valid_dist_days = []
        for d in dist_days:
            days_passed = i - d['index']
            # Chỉ giữ nếu <= 25 ngày và Index chưa tăng lấp quá 5% vùng xả
            if days_passed <= 25 and (c < d['close'] * 1.05):
                valid_dist_days.append(d)
        dist_days = valid_dist_days

        # 2. CHECK NEW DISTRIBUTION DAY
        # Giảm >= 0.2%, Vol > Vol hôm trước
        tr = h - l + 1e-10
        if pct_change <= -0.002 and v > pv:
            # Lọc nhiễu: Đóng cửa không được rút chân mạnh về đỉnh
            if (c - l) / tr < 0.6: 
                dist_days.append({
                    'index': i,
                    'close': c,
                    'date': df['Date'].iloc[i]
                })

        # 3. KIỂM TRA MẤT FTD (CÁC ĐIỀU KIỆN HUỶ)
        if ftd_active:
            # Thủng đáy Rally Day 1
            if l < ra_low:
                ftd_active = False
                ra_day = 0
            # Xuất hiện quá nhiều phân phối (>= 5 ngày xả áp lực)
            elif len(dist_days) >= 5:
                ftd_active = False
                ra_day = 0
            # Mất MA50 quá sâu (> 3% dưới MA50)
            elif c < ma50 * 0.97:
                ftd_active = False
                ra_day = 0

        # 4. RALLY ATTEMPT & FOLLOW-THROUGH DAY (Dò đáy mới)
        if not ftd_active:
            if ra_day > 0:
                if l < ra_low:
                    # Reset vì rơi lủng đáy nỗ lực hồi phục
                    ra_day = 0
                    ra_low = float('inf')
                else:
                    ra_day += 1
                    
                    # Test FTD (Từ ngày 4 trở lên, tăng > 1.2%, Volume lớn hơn hôm trước)
                    if ra_day >= 4 and pct_change >= 0.012 and v > pv:
                        ftd_active = True
                        # FTD thành công: Xóa một phần sương mù phân phối cũ (những cái > 10 ngày)
                        dist_days = [d for d in dist_days if i - d['index'] <= 10]
            
            # Khởi tạo RA Day 1: Phiên tăng điểm, đóng nến xanh sau đoạn rơi
            if ra_day == 0 and pct_change > 0 and c >= o:
                ra_day = 1
                ra_low = l

        # 5. ĐÁNH GIÁ REGIME
        if ftd_active:
            regime = "CONFIRMED UPTREND"
        else:
            # Sideway Mini Trend: Chạy trên MA50, số ngày xả kềm hãm <= 3
            if c > ma50 and len(dist_days) <= 3:
                regime = "SIDEWAY"
            else:
                regime = "MARKET IN CORRECTION"

    # ==================================
    # SUMMARY CHO PHIÊN CUỐI CÙNG
    # ==================================
    dist_count = len(dist_days)
    
    # Quyết định hành động Matrix
    if regime == "CONFIRMED UPTREND":
        action = "TRADE MẠNH" if dist_count <= 2 else ("GIẢM SIZE" if dist_count <= 4 else "NGUY HIỂM")
    elif regime == "SIDEWAY":
        action = "TRADE NHỎ"
    else:
        action = "KHÔNG TRADE"

    last_date = df['Date'].iloc[-1]
    
    result = {
        "date": last_date.strftime("%Y-%m-%d"),
        "regime": regime,
        "ftd_active": ftd_active,
        "ra_day": ra_day,
        "ra_low": round(ra_low, 2) if ra_low != float('inf') else None,
        "distribution_count": dist_count,
        "distribution_dates": [d['date'].strftime("%Y-%m-%d") for d in dist_days],
        "action": action
    }
    
    logger.info(f"Market Analysis (Date: {result['date']}): {regime} | Dist: {dist_count} | RA: {ra_day} | Action: {action}")
    return result

def analyze_market_breadth(data_dict: dict, vnindex_ticker="VNINDEX") -> dict:
    """
    Quét toàn bộ cổ phiếu trên data (data_dict) để đo độ rộng.
    Trả về tỷ lệ Mã Tăng/Giảm, Dòng tiền lan toả và Phân kỳ RSI (nếu có).
    Lưu ý: Yêu cầu data_dict chứa nhiều mã cổ phiếu của toàn thị trường.
    """
    total_stocks = 0
    up_stocks = 0
    down_stocks = 0
    flat_stocks = 0
    
    # Leader tracks
    breakout_count = 0
    strong_stocks = 0

    for ticker, df in list(data_dict.items()):
        if ticker in [vnindex_ticker, "HNXINDEX", "UPCOM"]:
            continue
            
        if len(df) < 20: 
            continue
            
        c = float(df['Close'].iloc[-1])
        pc = float(df['Close'].iloc[-2])
        v = float(df['Volume'].iloc[-1])
        av20 = float(df['Volume'].iloc[-20:].mean())
        
        total_stocks += 1
        pct = (c - pc) / pc
        if pct > 0.01:
            up_stocks += 1
        elif pct < -0.01:
            down_stocks += 1
        else:
            flat_stocks += 1
            
        # Check Breakout (Very basic proxy: nổ vol vượt đỉnh ngắn)
        highest_20 = df['High'].iloc[-21:-1].max() if len(df) > 21 else df['High'][:-1].max()
        if c > highest_20 and v > av20 * 1.5:
            breakout_count += 1
            
        # Dòng tiền giữ giá (Strong stock): Close > MA50
        ma50 = df['Close'].iloc[-50:].mean() if len(df) >= 50 else df['Close'].mean()
        if c > ma50:
            strong_stocks += 1

    breadth_ratio = "TỐT" if up_stocks > down_stocks * 1.5 else ("XẤU" if down_stocks > up_stocks * 1.5 else "CÂN BẰNG")
    
    return {
        "total_scanned": total_stocks,
        "advances": up_stocks,
        "declines": down_stocks,
        "unaltered": flat_stocks,
        "breadth_label": breadth_ratio,
        "breakout_leaders": breakout_count,
        "strong_stocks_pct": round(strong_stocks / total_stocks * 100, 1) if total_stocks > 0 else 0
    }

def evaluate_market_score(index_analysis: dict, breadth_analysis: dict) -> dict:
    """
    Chấm dứt điểm Thị Trường (Thang 10 điểm) dựa theo BREADTH + CANSLIM TREND.
    """
    score = 0
    
    # 1. Breadth tốt (Tăng > Giảm rõ rệt)
    if breadth_analysis['breadth_label'] == "TỐT":
        score += 2
    elif breadth_analysis['breadth_label'] == "CÂN BẰNG":
        score += 1
        
    # 2. Có Leader chạy (Có mã Breakout)
    if breadth_analysis['breakout_leaders'] >= 5:
        score += 2
    elif breadth_analysis['breakout_leaders'] >= 1:
        score += 1
        
    # 3. Ít Distribution
    d_count = index_analysis['distribution_count']
    if d_count <= 2:
        score += 2
    elif d_count <= 4:
        score += 1
        
    # 4. Trạng thái Regime (Thay thế Momentum & Volume Confirm vì đã tính trong FTD)
    if index_analysis['regime'] == "CONFIRMED UPTREND":
        score += 4
    elif index_analysis['regime'] == "SIDEWAY":
        score += 2
        
    health = "RẤT KHỎE" if score >= 8 else ("BÌNH THƯỜNG" if score >= 5 else "CÓ VẤN ĐỀ")
    
    return {
        "market_score": score,
        "health": health
    }

def analyze_momentum_divergence(df: pd.DataFrame) -> dict:
    """
    Tính RSI (14) và MACD (12, 26, 9) để dò tìm phân kỳ đỉnh (Bearish Divergence).
    Dựa trên sự đối chiếu so sánh đỉnh của 15 ngày qua với 15 ngày xa hơn.
    """
    if len(df) < 50:
        return {"rsi_val": 0, "macd_val": 0, "hist_val": 0, "rsi_divergence": False, "macd_divergence": False}

    # Tính RSI
    delta = df['Close'].diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(com=13, adjust=False).mean()
    ma_down = down.ewm(com=13, adjust=False).mean()
    rs = ma_up / ma_down
    rsi = 100 - (100 / (1 + rs))

    # Tính MACD
    ema_fast = df['Close'].ewm(span=12, adjust=False).mean()
    ema_slow = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=9, adjust=False).mean()
    hist = macd - sig

    # Tìm phân kỳ
    last_15 = df['Close'].iloc[-15:]
    prev_15 = df['Close'].iloc[-30:-15]
    
    price_top_1 = last_15.max()
    price_top_2 = prev_15.max()
    
    rsi_last_15 = rsi.iloc[-15:].max()
    rsi_prev_15 = rsi.iloc[-30:-15].max()
    
    macd_last_15 = macd.iloc[-15:].max()
    macd_prev_15 = macd.iloc[-30:-15].max()
    
    # Giá lập đỉnh cao hơn nhưng động lượng (RSI/MACD) yếu đi
    rsi_div = (price_top_1 > price_top_2) and (rsi_last_15 < rsi_prev_15 * 0.95)
    macd_div = (price_top_1 > price_top_2) and (macd_last_15 < macd_prev_15 * 0.90)

    # Đang ở vùng xấu (Quá mua cực đoan / momentum âm)
    is_rsi_weak = rsi.iloc[-1] < 40 or rsi.iloc[-1] > 75
    
    return {
        "rsi_val": round(rsi.iloc[-1], 2),
        "macd_val": round(macd.iloc[-1], 2),
        "hist_val": round(hist.iloc[-1], 2),
        "rsi_divergence": rsi_div,
        "macd_divergence": macd_div,
        "is_bad_zone": is_rsi_weak or (macd.iloc[-1] < 0 and hist.iloc[-1] < 0)
    }

def calculate_index_sr(df: pd.DataFrame) -> dict:
    """
    Tính vùng Hỗ trợ / Kháng cự cho Index theo thuật toán riêng.
    Cải tiến: Tìm đỉnh/đáy cục bộ trong 250 phiên để có dữ liệu tin cậy hơn.
    """
    if df is None or df.empty or len(df) < 200:
        return {"s1": 0, "s2": 0, "r1": 0, "r2": 0}

    cp = float(df['Close'].iloc[-1])
    # Sử dụng rolling().mean() an toàn hơn
    ma100_series = df['Close'].rolling(100).mean()
    ma200_series = df['Close'].rolling(200).mean()
    ma100 = float(ma100_series.iloc[-1]) if not pd.isna(ma100_series.iloc[-1]) else 0
    ma200 = float(ma200_series.iloc[-1]) if not pd.isna(ma200_series.iloc[-1]) else 0

    # 1. Thu thập các Đỉnh (Peaks) và Đáy (Valleys) cục bộ trong 250 phiên
    lookback = min(250, len(df) - 10)
    peaks = []
    valleys = []
    
    # Quét từ quá khứ đến sát hiện tại (loại bỏ 2 nến cuối để tránh nhiễu nến đang chạy)
    for i in range(len(df) - lookback, len(df) - 2):
        # Window 5 phiên xung quanh (tổng 11) để xác định điểm xoay (Pivot)
        if i < 5: continue
        window_high = df['High'].iloc[i-5:i+6].max()
        window_low = df['Low'].iloc[i-5:i+6].min()
        
        val_high = float(df['High'].iloc[i])
        val_low = float(df['Low'].iloc[i])
        
        if val_high == window_high:
            peaks.append(val_high)
        if val_low == window_low:
            valleys.append(val_low)

    # Loại bỏ trùng lặp và sắp xếp
    peaks = sorted(list(set(peaks)))
    valleys = sorted(list(set(valleys)))

    # A: Đỉnh ngắn hạn (gần nhất/cao nhất) mà tại đó cp > A
    A_candidates = [p for p in peaks if p < cp]
    A = max(A_candidates) if A_candidates else None

    # C: Đáy gần nhất có giá < A (nếu tìm thấy A)
    C = None
    if A:
        c_candidates = [v for v in valleys if v < A]
        C = max(c_candidates) if c_candidates else None

    # B: Đáy (Valley) mà tại đó B > cp (Kháng cự)
    B_candidates = [v for v in valleys if v > cp]
    B = min(B_candidates) if B_candidates else None

    # 2. Tính Hỗ trợ (S)
    s_candidates = []
    if A: s_candidates.append(A)
    if C: s_candidates.append(C)
    if ma100 > 0 and cp > ma100: s_candidates.append(ma100)
    if ma200 > 0 and cp > ma200: s_candidates.append(ma200)

    # Quy tắc: s1 = max, s2 = max thứ 2
    s_candidates = sorted(list(set(s_candidates)), reverse=True)
    s1 = s_candidates[0] if len(s_candidates) > 0 else 0
    s2 = s_candidates[1] if len(s_candidates) > 1 else 0

    # 3. Tính Kháng cự (R)
    r_candidates = []
    if B: r_candidates.append(B)
    # Các đỉnh cao hơn giá hiện tại cũng là kháng cự
    r_peaks = [p for p in peaks if p > cp]
    if r_peaks: r_candidates.extend(r_peaks[:2]) # Lấy 2 đỉnh gần nhất phía trên
    
    if ma100 > 0 and ma100 > cp: r_candidates.append(ma100)
    if ma200 > 0 and ma200 > cp: r_candidates.append(ma200)

    r_candidates = sorted(list(set(r_candidates)))
    r1 = r_candidates[0] if len(r_candidates) > 0 else 0
    r2 = r_candidates[1] if len(r_candidates) > 1 else 0

    return {
        "s1": round(s1, 2),
        "s2": round(s2, 2),
        "r1": round(r1, 2),
        "r2": round(r2, 2)
    }
