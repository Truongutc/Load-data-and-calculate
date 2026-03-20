import pandas as pd

def analyze_accumulation(df: pd.DataFrame) -> dict:
    if len(df) < 50:
        return {"is_accumulation": False, "base_quality": "NONE", "ready_to_break": False, "notes": []}
        
    last = df.iloc[-1]
    
    # Calculate required indicators
    hh20 = df['High'].rolling(20).max().iloc[-1]
    ll20 = df['Low'].rolling(20).min().iloc[-1]
    
    close = last['Close']
    
    # 1. Biên độ giá thu hẹp
    # HIGH: < 7%, MEDIUM: < 12%
    price_range = (hh20 - ll20) / close
    price_tight = price_range < 0.12
    
    # 2. Volume giảm
    vol_sma10 = df['Volume'].rolling(10).mean().iloc[-1]
    vol_sma20 = df['Volume'].rolling(20).mean().iloc[-1]
    vol_avg_low = vol_sma10 < vol_sma20 * 1.3
    
    # 3. Giá giữ quanh MA20
    ma20 = df['Close'].rolling(20).mean().iloc[-1]
    near_ma20 = close >= ma20 * 0.98 # Allow 2% dip for sideway
    
    # 4. Có tín hiệu VSA trong 7 phiên (window rộng hơn)
    def check_vsa_at(d, i):
        if abs(i) >= len(d): return False
        c, o, v = d['Close'].iloc[i], d['Open'].iloc[i], d['Volume'].iloc[i]
        s = d['High'].iloc[i] - d['Low'].iloc[i]
        vs20 = d['Volume'].rolling(20).mean().iloc[i]
        as20 = (d['High'] - d['Low']).rolling(20).mean().iloc[i]
        if pd.isna(vs20) or pd.isna(as20): return False
        
        no_s = (c < o) and (v < vs20) and (s < as20)
        ts_s = (c < o) and (s < as20) and (v < d['Volume'].iloc[i-1]) and (v < d['Volume'].iloc[i-2])
        return no_s or ts_s

    vsa_recently = any([check_vsa_at(df, -1-i) for i in range(7)])
    
    # Logic: Tích nền = Biên độ hẹp + Volume thấp + Giữ được vùng giá (Above S1/MA20)
    is_accum = price_tight and vol_avg_low and near_ma20
    
    notes = []
    if price_range < 0.07: notes.append("Nền thắt chặt (Tight Base <7%)")
    elif price_tight: notes.append("Biên độ bắt đầu thu hẹp (<12%)")
    if vol_avg_low: notes.append("Áp lực bán cạn kiệt (Volume low)")
    if vsa_recently: notes.append("Xuất hiện điểm cạn cung (No/Test Supply)")
    
    quality = "HIGH" if (is_accum and vsa_recently and price_range < 0.08) else "MEDIUM"

    return {
        "is_accumulation": is_accum,
        "base_quality": quality,
        "ready_to_break": is_accum and (close > ma20) and vsa_recently,
        "notes": notes,
        "range_pct": round(price_range * 100, 2)
    }
