import pandas as pd
import numpy as np

def evaluate_ma(df: pd.DataFrame, idx: int = -1) -> dict:
    """"Phân tích hành vi thị trường dựa trên hệ thống Đường Trung Bình Động (MA)."""
    if len(df) < abs(idx) + 200: # Cần dữ liệu đủ sâu cho MA200, xử lý an toàn
        # Nếu chưa đủ 200 phiên, fallback chạy bộ MA ngắn
        has_ma200 = False
    else:
        has_ma200 = True
        
    if len(df) < abs(idx) + 50:
        return {"status": "Không đủ dữ liệu chạy MA", "action": "N/A"}
        
    last = df.iloc[idx]
    prev1 = df.iloc[idx-1]
    prev5 = df.iloc[idx-5] if len(df) >= abs(idx)+5 else prev1
    
    price = float(last['Close'])
    ma20 = float(last.get('MA20', price))
    ma50 = float(last.get('MA50', price))
    ma200 = float(last.get('MA200', price)) if has_ma200 and 'MA200' in df.columns and not pd.isna(last.get('MA200')) else None
    
    ma20_prev = float(prev1.get('MA20', ma20))
    ma50_prev = float(prev1.get('MA50', ma50))
    
    ma20_slope = (ma20 - float(prev5.get('MA20', ma20))) / 5
    ma50_slope = (ma50 - float(prev5.get('MA50', ma50))) / 5
    
    # Check if MAs are "dốc lên" (Rising)
    is_ma20_rising = ma20 > ma20_prev and ma20_slope > 0
    is_ma50_rising = ma50 > ma50_prev and ma50_slope > 0
    is_ma_flat = abs(ma20_slope) < (price * 0.001) # Rất phẳng
    
    status = []
    action = []
    
    # 🌟 ĐỘ KHỎE (MOMENTUM) & VỊ TRÍ GIÁ
    distance_to_ma20 = (price - ma20) / ma20
    is_too_far = distance_to_ma20 > 0.07 # Cách xa > 7%
    is_near_ma20 = -0.015 <= distance_to_ma20 <= 0.03 # Giá quanh MA20
    
    # 🌟 TẦNG 1: XU HƯỚNG & 4 TRẠNG THÁI THỊ TRƯỜNG
    
    # TẦNG 1: UPTREND CHUẨN
    if ma200 is not None:
        is_perfect_uptrend = price > ma20 > ma50 > ma200
        is_downtrend = price < ma20 < ma50 < ma200
    else:
        is_perfect_uptrend = price > ma20 > ma50
        is_downtrend = price < ma20 < ma50
        
    # TRẠNG THÁI 1: STRONG TREND
    if is_perfect_uptrend and is_ma20_rising and is_ma50_rising:
        if is_too_far:
            status.append("BẪY: Giá quá xa MA20 trong Strong Trend.")
            action.append("90% dính Pullback. Không FOMO mua đuổi, chờ giá hãm phanh.")
        elif is_near_ma20:
            status.append("STRONG TREND (Kèo ngon): Giá > MA20 > MA50 > 200, các đường MA dốc lên.")
            action.append("Chỉ BUY Pullback. Entry cực đẹp quanh MA20 hoặc MA50.")
        else:
            status.append("STRONG TREND: Xu hướng mạnh (MA xếp lớp chuẩn).")
            action.append("Dòng tiền đang vào, ưu tiên nắm giữ theo trend.")
            
    # TRẠNG THÁI 2: EARLY TREND
    elif price > ma50 and float(prev5['Close']) <= float(prev5.get('MA50', price)) and is_ma50_rising:
        status.append("EARLY TREND: Giá vừa vượt MA50 và MA50 bắt đầu xoay lên.")
        action.append("Trend mới nhú, có thể MUA SỚM (Risk cao hơn).")
        
    # TRẠNG THÁI 4: TREND GÃY
    elif float(prev5['Close']) > float(prev5.get('MA20', price)) and price < ma20 and price < ma50:
        status.append("TREND GÃY: Giá thủng MA20 sau đó đục luôn cả bờ đê MA50.")
        action.append("Xu hướng tăng đã chết. CANH EXIT / CẮT LỖ KHẨN CẤP.")
        
    # XU HƯỚNG: DOWNTREND
    elif is_downtrend:
        if ma20 < ma50 and ma20_slope < 0:
            status.append("DOWNTREND Chuẩn: Giá < MA20 < MA50, xu hướng cắm đầu.")
            action.append("Tuyệt đối KHÔNG BẮT ĐÁY, tránh xa Setup này.")
            
    # TRẠNG THÁI 3: SIDEWAY
    elif not is_perfect_uptrend and not is_downtrend:
        # Cross lên cắt xuống liên tục hoặc giá quấn quanh MA20/50
        cross_up = ma20 > ma50 and ma20_prev <= ma50_prev
        cross_down = ma20 < ma50 and ma20_prev >= ma50_prev
        if is_ma_flat or cross_up or cross_down:
            status.append("SIDEWAY / WHIPSAW: Giá quấn quanh MA, đường MA nằm ngang.")
            action.append("Thị trường đi ngang nhiễu loạn, bị vả liên tục nếu đánh Trend. BỎ QUA.")
            
    # 🌟 CÁC SETUP KIẾM TIỀN THEO MA
    
    # Breakout Đỉnh (Swing High) và MA20 Support
    past_swings = [h for h in df['SwingHigh'].iloc[-15:idx] if h > 0]
    if past_swings and price > past_swings[-1] and price > ma20 and is_ma20_rising:
        status.append("SETUP 3 (BREAKOUT + MA SUPPORT): Giá phá đỉnh, MA20 nâng đỡ dưới chân.")
        action.append("Trend được củng cố. Tiếp tục HOLD dồn vị thế.")
        
    # Setup 1 & 2: Pullback và Bounce
    # Check nếu nến hiện tại xanh (Open < Close) và chạm hỗ trợ
    if price > float(last['Open']): # Nến tăng
        low_price = float(last['Low'])
        # Chạm MA20 và Rút Chân
        if low_price <= ma20 and price > ma20 and is_perfect_uptrend:
            status.append("SETUP 1 (PULLBACK MA20): Kèo ăn dày nhất. Giá test MA20 thành công.")
            action.append("BUY MẠNH. Hỗ trợ MA20 đã đỡ giá tốt trong Uptrend.")
        # Chạm MA50 và Rút Chân
        elif low_price <= ma50 and price > ma50 and ma50_slope > 0:
            status.append("SETUP 2 (MA50 BOUNCE): Chạm hỗ trợ trung hạn MA50 và bật lên.")
            action.append("BUY AN TOÀN. Mức RR (Risk/Reward) lúc này là rất tốt.")
            
    # Xử lý BẪY TRẬP
    if is_ma_flat and price > ma20:
        status.append("BẪY MOMENTUM: Giá nằm trên MA20 nhưng MA20 phẳng lì.")
        action.append("Dòng tiền yểu điệu, không phải Trend khỏe thực thụ.")
        
    if ma200 is not None:
        golden_cross = ma50 > ma200 and ma50_prev <= float(prev1.get('MA200', ma200))
        if golden_cross:
            status.append("BẪY CHẾT NGƯỜI: Golden Cross (MA50 cắt MA200) vừa xảy ra.")
            action.append("Tín hiệu có độ trễ cực cao (Lag nặng). Thận trọng vì giá đa phần đã xả hàng lúc này.")

    # FALLBACK NẾU KHÔNG VÀO CASE NÀO
    if not status:
        status.append(f"Giá nằm {'Tên' if price > ma20 else 'Dưới'} MA20, thiếu xung lực rõ ràng.")
        action.append("Quan sát thêm các mốc giá, chưa có Setup chuẩn theo MA.")

    return {
        "status": status[0] if len(status) == 1 else "\n".join("- " + s for s in status),
        "action": action[0] if len(action) == 1 else "\n".join("- " + a for a in action)
    }
