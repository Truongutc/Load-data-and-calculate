"""
Module 8 – Market Regime Engine (v2.0 – 7 States)
===================================================
Analyzes Index data (VNINDEX, HNXINDEX) to evaluate CANSLIM Market conditions:
- Distribution Days
- Rally Attempts (RA) – chỉ kích hoạt sau cú giảm > 10%
- Follow-Through Days (FTD) – ngày 4-7 mạnh, ngày 8+ yếu
- 7 trạng thái thị trường chi tiết

Returns the current Market Regime, safety scores, and action recommendations.
"""

import logging
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

def analyze_market_index(df_index: pd.DataFrame, breadth_pct_ma20: float = 50.0,
                         breadth_pct_ma50: float = 50.0, momentum_data: dict = None) -> dict:
    """
    Quét dữ liệu VNINDEX để xác định trạng thái thị trường chung.
    Phiên bản 2.0: 7 trạng thái, RA chỉ sau giảm >10%, FTD phân loại mạnh/yếu.

    Parameters
    ----------
    df_index : pd.DataFrame - Dữ liệu Index (OHLCV + Date)
    breadth_pct_ma20 : float - % cổ phiếu nằm trên MA20 (từ breadth engine)
    breadth_pct_ma50 : float - % cổ phiếu nằm trên MA50 (từ breadth engine)
    momentum_data : dict - Dữ liệu phân kỳ RSI/MACD (từ momentum engine)
    """
    if df_index is None or df_index.empty or len(df_index) < 50:
        return {
            "regime": "UNKNOWN",
            "ftd_active": False,
            "ftd_quality": None,
            "ra_day": 0,
            "distribution_count": 0,
            "distribution_dates": [],
            "action": "STANDBY",
            "decline_from_peak_pct": 0
        }

    mom = momentum_data or {}

    df = df_index.copy()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()

    # Kijun 26
    hi26 = df['High'].rolling(26).max()
    lo26 = df['Low'].rolling(26).min()
    df['Kijun'] = (hi26 + lo26) / 2

    regime = "DOWNTREND"
    ra_day = 0
    ra_low = float('inf')
    ftd_active = False
    ftd_quality = None  # "STRONG" hoặc "WEAK"
    ftd_low = float('inf')  # Giá thấp nhất của phiên FTD
    dist_days = []

    # Track đỉnh gần nhất để tính % giảm
    rolling_peak = float(df['Close'].iloc[0])
    decline_triggered_8 = False  # True khi giảm > 8% từ đỉnh (cho RECOVERY)
    decline_triggered_10 = False  # True khi giảm > 10% từ đỉnh (cho RA/FTD/STABLE_RECOVERY)

    for i in range(1, len(df)):
        c = float(df['Close'].iloc[i])
        o = float(df['Open'].iloc[i])
        h = float(df['High'].iloc[i])
        l = float(df['Low'].iloc[i])
        v = float(df['Volume'].iloc[i])

        pc = float(df['Close'].iloc[i-1])
        pv = float(df['Volume'].iloc[i-1])

        ma10 = float(df['MA10'].iloc[i]) if not pd.isna(df['MA10'].iloc[i]) else c
        ma20 = float(df['MA20'].iloc[i]) if not pd.isna(df['MA20'].iloc[i]) else c
        ma50 = float(df['MA50'].iloc[i]) if not pd.isna(df['MA50'].iloc[i]) else c
        kijun = float(df['Kijun'].iloc[i]) if not pd.isna(df['Kijun'].iloc[i]) else c

        pct_change = (c - pc) / pc
        tr = h - l + 1e-10

        # Cập nhật đỉnh gần nhất
        if c > rolling_peak:
            rolling_peak = c
            decline_triggered_8 = False
            decline_triggered_10 = False

        # Kiểm tra mức giảm từ đỉnh
        decline_pct = (rolling_peak - c) / rolling_peak
        if decline_pct >= 0.08:
            decline_triggered_8 = True
        if decline_pct >= 0.10:
            decline_triggered_10 = True

        # 1. CLEAN UP DISTRIBUTION DAYS
        valid_dist_days = []
        for d in dist_days:
            days_passed = i - d['index']
            if days_passed <= 25 and (c < d['close'] * 1.05):
                valid_dist_days.append(d)
        dist_days = valid_dist_days

        # 2. CHECK NEW DISTRIBUTION DAY
        if pct_change <= -0.002 and v > pv:
            if (c - l) / tr < 0.6:
                dist_days.append({
                    'index': i,
                    'close': c,
                    'date': df['Date'].iloc[i]
                })

        # 3. KIỂM TRA MẤT FTD (CÁC ĐIỀU KIỆN HUỶ)
        if ftd_active:
            # Điều kiện 1: Giá thủng mức thấp nhất của phiên FTD
            if l < ftd_low:
                ftd_active = False
                ftd_quality = None
                ftd_low = float('inf')
                ra_day = 0
            # Điều kiện 2: Thị trường giảm trên 10% từ đỉnh
            elif decline_pct >= 0.10:
                ftd_active = False
                ftd_quality = None
                ftd_low = float('inf')
                ra_day = 0

        # 4. RALLY ATTEMPT & FOLLOW-THROUGH DAY
        # CHỈ BẮT ĐẦU TÌM RA SAU KHI GIẢM > 10%
        if not ftd_active:
            if ra_day > 0:
                # Reset nếu giá ĐÓNG CỬA thấp hơn giá thấp nhất của phiên RA Day 1
                if c < ra_low:
                    ra_day = 0
                    ra_low = float('inf')
                else:
                    ra_day += 1

                    # Tính Vol trung bình 20 phiên
                    avg_vol_20 = float(df['Volume'].iloc[max(0,i-20):i].mean()) if i >= 20 else v

                    # Test FTD (Từ ngày 4 trở lên)
                    if ra_day >= 4 and pct_change >= 0.012 and v > pv and v > avg_vol_20:
                        ftd_active = True
                        ftd_low = l  # Lưu giá thấp nhất của phiên FTD
                        # Phân loại FTD mạnh/yếu
                        if ra_day <= 7:
                            ftd_quality = "STRONG"
                        else:
                            ftd_quality = "WEAK"
                        # FTD mạnh hơn nếu tăng > 1.5%
                        if pct_change >= 0.015 and ra_day <= 7:
                            ftd_quality = "STRONG"
                        # Xóa một phần phân phối cũ
                        dist_days = [d for d in dist_days if i - d['index'] <= 10]

            # Khởi tạo RA Day 1 – CHỈ KHI ĐÃ GIẢM > 10%
            if ra_day == 0 and decline_triggered_10:
                # Điều kiện 1: Tạo đáy mới nhưng rút chân đóng cửa ở nửa trên thanh nến
                candle_body_upper = (c - l) / tr > 0.5 and c > (h + l) / 2
                # Điều kiện 2: Phiên tăng điểm sau chuỗi giảm
                is_green_after_decline = pct_change > 0 and c >= o

                if candle_body_upper or is_green_after_decline:
                    ra_day = 1
                    ra_low = l

    # ==================================
    # PHIÊN CUỐI CÙNG – PHÂN LOẠI 7 TRẠNG THÁI
    # ==================================
    last_idx = len(df) - 1
    c_last = float(df['Close'].iloc[-1])
    ma10_last = float(df['MA10'].iloc[-1]) if not pd.isna(df['MA10'].iloc[-1]) else c_last
    ma20_last = float(df['MA20'].iloc[-1]) if not pd.isna(df['MA20'].iloc[-1]) else c_last
    ma50_last = float(df['MA50'].iloc[-1]) if not pd.isna(df['MA50'].iloc[-1]) else c_last
    kijun_last = float(df['Kijun'].iloc[-1]) if not pd.isna(df['Kijun'].iloc[-1]) else c_last

    dist_count = len(dist_days)
    decline_from_peak = (rolling_peak - c_last) / rolling_peak
    has_divergence = mom.get('rsi_divergence', False) or mom.get('macd_divergence', False)

    # Tính MA50 slope (hướng MA50)
    if len(df) >= 55 and not pd.isna(df['MA50'].iloc[-5]):
        ma50_5d_ago = float(df['MA50'].iloc[-5])
        ma50_slope_pct = (ma50_last - ma50_5d_ago) / (ma50_5d_ago + 1e-10)
    else:
        ma50_slope_pct = 0

    # Tính MA10 slope
    if len(df) >= 13 and not pd.isna(df['MA10'].iloc[-3]):
        ma10_3d_ago = float(df['MA10'].iloc[-3])
        ma10_slope_pct = (ma10_last - ma10_3d_ago) / (ma10_3d_ago + 1e-10)
    else:
        ma10_slope_pct = 0

    ma50_flat = abs(ma50_slope_pct) < 0.001  # MA50 đi ngang
    price_near_ma50 = abs(c_last - ma50_last) / (ma50_last + 1e-10) < 0.02  # Giá ±2% MA50

    # ---- PHÂN LOẠI 7 TRẠNG THÁI ----
    if ftd_active and c_last > ma50_last and dist_count <= 3 and breadth_pct_ma20 > 60:
        # 1. UPTREND – Thị trường tăng giá xác nhận
        regime = "UPTREND"
        action = "TRADE MẠNH – Tập trung mua Leader vượt đỉnh, có thể dùng Margin"

    elif ftd_active and c_last > ma50_last and (dist_count >= 4 or has_divergence):
        # 2. UPTREND UNDER PRESSURE – Uptrend tiềm ẩn rủi ro
        regime = "UPTREND_UNDER_PRESSURE"
        action = "KHÔNG MUA ĐUỔI – Chốt lời từng phần, nâng chặn lãi, thu hẹp danh mục"

    elif decline_triggered_10 and ftd_active and breadth_pct_ma20 > 40 and c_last < ma50_last and (c_last > ma20_last or c_last > kijun_last):
        # 7. HỒI PHỤC ỔN ĐỊNH – Đã có FTD sau cú rơi >10%, giá > MA20/Kijun nhưng < MA50
        regime = "STABLE_RECOVERY"
        action = "TĂNG TỈ TRỌNG 50-75% – Tập trung Leader, có thể mua tích nền"

    elif decline_triggered_8 and not ftd_active and ra_day >= 2 and c_last > ma10_last and ma10_slope_pct > 0:
        # 6. HỒI PHỤC – Sau cú rơi >8%, có 2-3 phiên RA, breadth bắt đầu tăng
        regime = "RECOVERY"
        action = "THĂM DÒ 10-20% – Mua cổ phiếu khỏe hơn thị trường, tín hiệu mạnh"

    elif price_near_ma50 and ma50_flat:
        # 3. SIDEWAY – Giá dao động quanh MA50
        regime = "SIDEWAY"
        action = "SWING TRADE TẠI HỖ TRỢ – Tỷ trọng 20-30% tiền mặt"

    elif c_last < ma50_last and c_last >= ma50_last * 0.97 and (dist_count > 5 or breadth_pct_ma20 < 40):
        # 4. SUY YẾU – Giá thủng MA50 nhưng chưa sâu
        regime = "MARKET_WEAKENING"
        action = "TIỀN MẶT TỐI THIỂU 50% – Không bắt đáy, chờ tín hiệu rõ ràng"

    elif c_last < ma50_last * 0.97 or decline_from_peak >= 0.10:
        # 5. DOWNTREND – Giá dưới MA50 > 3% hoặc giảm > 10%
        regime = "DOWNTREND"
        action = "ĐỨNG NGOÀI – Giữ tiền, chờ Nỗ lực hồi phục + FTD mới"

    else:
        # Fallback: Sideway nhẹ
        regime = "SIDEWAY"
        action = "SWING TRADE TẠI HỖ TRỢ – Tỷ trọng 20-30% tiền mặt"

    last_date = df['Date'].iloc[-1]

    result = {
        "date": last_date.strftime("%Y-%m-%d"),
        "regime": regime,
        "ftd_active": ftd_active,
        "ftd_quality": ftd_quality,
        "ra_day": ra_day,
        "ra_low": round(ra_low, 2) if ra_low != float('inf') else None,
        "distribution_count": dist_count,
        "distribution_dates": [d['date'].strftime("%Y-%m-%d") for d in dist_days],
        "action": action,
        "decline_from_peak_pct": round(decline_from_peak * 100, 2)
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
    strong_stocks_ma50 = 0
    strong_stocks_ma20 = 0

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

        # Dòng tiền giữ giá: Close > MA50
        ma50 = df['Close'].iloc[-50:].mean() if len(df) >= 50 else df['Close'].mean()
        if c > ma50:
            strong_stocks_ma50 += 1

        # Close > MA20
        ma20 = df['Close'].iloc[-20:].mean() if len(df) >= 20 else df['Close'].mean()
        if c > ma20:
            strong_stocks_ma20 += 1

    breadth_ratio = "TỐT" if up_stocks > down_stocks * 1.5 else ("XẤU" if down_stocks > up_stocks * 1.5 else "CÂN BẰNG")

    return {
        "total_scanned": total_stocks,
        "advances": up_stocks,
        "declines": down_stocks,
        "unaltered": flat_stocks,
        "breadth_label": breadth_ratio,
        "breakout_leaders": breakout_count,
        "strong_stocks_pct": round(strong_stocks_ma50 / total_stocks * 100, 1) if total_stocks > 0 else 0,
        "strong_stocks_ma20_pct": round(strong_stocks_ma20 / total_stocks * 100, 1) if total_stocks > 0 else 0
    }

def evaluate_market_score(index_analysis: dict, breadth_analysis: dict) -> dict:
    """
    Chấm điểm Thị Trường (Thang 10 điểm) dựa theo BREADTH + CANSLIM TREND.
    Cập nhật cho 7 trạng thái.
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

    # 4. Trạng thái Regime
    regime = index_analysis['regime']
    if regime == "UPTREND":
        score += 4
    elif regime == "UPTREND_UNDER_PRESSURE":
        score += 3
    elif regime == "STABLE_RECOVERY":
        score += 3
    elif regime == "RECOVERY":
        score += 2
    elif regime == "SIDEWAY":
        score += 2
    elif regime == "MARKET_WEAKENING":
        score += 1
    # DOWNTREND: +0

    # Clamp
    score = max(0, min(10, score))

    if score >= 8:
        health = "RẤT KHỎE"
    elif score >= 6:
        health = "KHỎE"
    elif score >= 4:
        health = "BÌNH THƯỜNG"
    elif score >= 2:
        health = "CÓ VẤN ĐỀ"
    else:
        health = "NGUY HIỂM"

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
        return {"rsi_val": 0, "macd_val": 0, "hist_val": 0, "rsi_divergence": False, "macd_divergence": False, "is_bad_zone": False}

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
        "rsi_val": round(float(rsi.iloc[-1]), 2),
        "macd_val": round(float(macd.iloc[-1]), 2),
        "hist_val": round(float(hist.iloc[-1]), 2),
        "rsi_divergence": bool(rsi_div),
        "macd_divergence": bool(macd_div),
        "is_bad_zone": bool(is_rsi_weak or (macd.iloc[-1] < 0 and hist.iloc[-1] < 0))
    }

def calculate_index_sr(df: pd.DataFrame) -> dict:
    """
    Tính vùng Hỗ trợ / Kháng cự cho Index theo thuật toán riêng.
    Cải tiến: Tìm đỉnh/đáy cục bộ trong 250 phiên để có dữ liệu tin cậy hơn.
    """
    if df is None or df.empty or len(df) < 50:
        return {"s1": 0, "s2": 0, "r1": 0, "r2": 0}

    cp = float(df['Close'].iloc[-1])
    
    # 0. Tính toán các chỉ báo bổ trợ
    ma20_s = df['Close'].rolling(20).mean()
    ma100_s = df['Close'].rolling(100).mean()
    ma200_s = df['Close'].rolling(200).mean()
    
    ma20 = float(ma20_s.iloc[-1]) if not pd.isna(ma20_s.iloc[-1]) else 0
    ma100 = float(ma100_s.iloc[-1]) if not pd.isna(ma100_s.iloc[-1]) else 0
    ma200 = float(ma200_s.iloc[-1]) if not pd.isna(ma200_s.iloc[-1]) else 0
    
    # Kijun (Đường trung bình 26 phiên của High/Low)
    hi26 = df['High'].rolling(26).max()
    lo26 = df['Low'].rolling(26).min()
    kijun = float((hi26.iloc[-1] + lo26.iloc[-1]) / 2) if not (pd.isna(hi26.iloc[-1]) or pd.isna(lo26.iloc[-1])) else 0

    # 1. Thu thập các Đỉnh (Peaks) và Đáy (Valleys) cục bộ trong 250 phiên
    lookback = min(250, len(df) - 10)
    peaks = []
    valleys = []
    
    # Quét từ quá khứ đến sát hiện tại (loại bỏ 2 nến cuối để tránh nhiễu nến đang chạy)
    for i in range(len(df) - lookback, len(df) - 2):
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

    # 2. Tính Hỗ trợ (S)
    s_candidates = []
    
    # - Đỉnh cũ đã vượt qua gần nhất (Peak < cp, lấy max)
    peaks_below = [p for p in peaks if p < cp]
    if peaks_below:
        s_candidates.append(max(peaks_below))
        
    # - Đáy cũ đã vượt qua gần nhất bên dưới (Valley < cp, lấy max)
    # - Đáy cũ thứ 2 đã vượt qua thấp hơn (Valley < cp, lấy max thứ 2)
    valleys_below = sorted([v for v in valleys if v < cp], reverse=True)
    if len(valleys_below) >= 1:
        s_candidates.append(valleys_below[0])
    if len(valleys_below) >= 2:
        s_candidates.append(valleys_below[1])
        
    # - MA100, MA200 nếu giá hiện tại đang nằm trên chúng
    if ma100 > 0 and cp > ma100: s_candidates.append(ma100)
    if ma200 > 0 and cp > ma200: s_candidates.append(ma200)

    # Quy tắc: s1 = max, s2 = max thứ 2 (s2 < s1)
    s_candidates = sorted(list(set(s_candidates)), reverse=True)
    s1 = s_candidates[0] if len(s_candidates) > 0 else 0
    s2 = s_candidates[1] if len(s_candidates) > 1 else 0

    # 3. Tính Kháng cự (R)
    r_candidates = []
    
    # - Đáy cũ phía trên giá hiện tại (Valley > cp, lấy min)
    valleys_above = [v for v in valleys if v > cp]
    if valleys_above:
        r_candidates.append(min(valleys_above))
        
    # - Đỉnh gần nhất phía trên giá hiện tại (Peak > cp, lấy min)
    peaks_above = [p for p in peaks if p > cp]
    if peaks_above:
        r_candidates.append(min(peaks_above))
        
    # - MA100, MA200 nếu giá hiện tại nằm dưới chúng
    if ma100 > 0 and cp < ma100: r_candidates.append(ma100)
    if ma200 > 0 and cp < ma200: r_candidates.append(ma200)
    
    # - Đường MA20 nếu giá hiện tại nằm dưới MA20
    if ma20 > 0 and cp < ma20: r_candidates.append(ma20)
    
    # - Đường Kijun nếu giá hiện tại nằm dưới Kijun
    if kijun > 0 and cp < kijun: r_candidates.append(kijun)

    # Quy tắc: r1 = min, r2 = min thứ 2 (r2 > r1)
    r_candidates = sorted(list(set(r_candidates)))
    r1 = r_candidates[0] if len(r_candidates) > 0 else 0
    r2 = r_candidates[1] if len(r_candidates) > 1 else 0

    return {
        "s1": round(s1, 2),
        "s2": round(s2, 2),
        "r1": round(r1, 2),
        "r2": round(r2, 2)
    }
