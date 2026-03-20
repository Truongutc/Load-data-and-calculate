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
    price_tight = ((hh20 - ll20) / close) < 0.15
    
    # 2. Volume giảm
    vol_sma10 = df['Volume'].rolling(10).mean().iloc[-1]
    vol_sma20 = df['Volume'].rolling(20).mean().iloc[-1]
    vol_drying = vol_sma10 < vol_sma20
    
    # 3. Giá giữ trên MA20
    ma20 = df['Close'].rolling(20).mean().iloc[-1]
    above_ma20 = close >= ma20
    
    # 4. Có tín hiệu VSA (No Supply or Test Supply)
    open_c = last['Open']
    vol = last['Volume']
    spread = last['High'] - last['Low']
    
    avg_spread_20 = (df['High'] - df['Low']).rolling(20).mean().iloc[-1]
    is_down = close < open_c
    
    # No Supply
    no_supply = is_down and (vol < vol_sma20) and (spread < avg_spread_20)
    
    # Test Supply
    prev_vol = df['Volume'].iloc[-2]
    prev2_vol = df['Volume'].iloc[-3]
    test_supply = is_down and (spread < avg_spread_20) and (vol < prev_vol) and (vol < prev2_vol)
    
    vsa_signal = no_supply or test_supply
    
    is_accum = price_tight and vol_drying and above_ma20 and vsa_signal
    
    notes = []
    if price_tight: notes.append("Biên độ hẹp")
    if vol_drying: notes.append("Volume cạn")
    if vsa_signal: notes.append("Tín hiệu cạn cung (No/Test Supply)")
    
    return {
        "is_accumulation": is_accum,
        "base_quality": "HIGH" if is_accum else "MEDIUM",
        "ready_to_break": is_accum and (close > ma20),
        "notes": notes
    }
