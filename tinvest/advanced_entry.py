import pandas as pd
import numpy as np

def calculate_ha(df: pd.DataFrame) -> pd.DataFrame:
    df_ha = pd.DataFrame(index=df.index)
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    
    ha_open = np.zeros(len(df))
    ha_open[0] = (df['Open'].iloc[0] + df['Close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i-1] + df_ha['HA_Close'].iloc[i-1]) / 2
    df_ha['HA_Open'] = ha_open
    return df_ha

def classify_entry(df: pd.DataFrame) -> dict:
    if len(df) < 200:
        return {"entry_type": "NONE", "confidence": "NONE", "position_size": "0%", "risk_flags": []}
        
    df = df.copy()
    
    # --- INDICATORS ---
    # MA
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA50'] = df['Close'].rolling(50).mean()
    df['MA100'] = df['Close'].rolling(100).mean()
    df['MA200'] = df['Close'].rolling(200).mean()
    
    # Ichimoku
    high_9 = df['High'].rolling(9).max()
    low_9 = df['Low'].rolling(9).min()
    df['Tenkan'] = (high_9 + low_9) / 2
    
    high_26 = df['High'].rolling(26).max()
    low_26 = df['Low'].rolling(26).min()
    df['Kijun'] = (high_26 + low_26) / 2
    
    df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
    
    high_52 = df['High'].rolling(52).max()
    low_52 = df['Low'].rolling(52).min()
    df['SpanB'] = ((high_52 + low_52) / 2).shift(26)
    
    df['CloudTop'] = df[['SpanA', 'SpanB']].max(axis=1)
    df['CloudBottom'] = df[['SpanA', 'SpanB']].min(axis=1)
    
    # Heikin Ashi
    df_ha = calculate_ha(df)
    df['HA_Open'] = df_ha['HA_Open']
    df['HA_Close'] = df_ha['HA_Close']
    df['HA_Color'] = np.where(df['HA_Close'] > df['HA_Open'], 'Green', 'Red')
    
    # VSA Proxy
    df['Spread'] = df['High'] - df['Low']
    df['AvgVolume20'] = df['Volume'].rolling(20).mean()
    df['Avg_Spread_20'] = df['Spread'].rolling(20).mean()
    
    # VSA Rules
    df['Stopping_Vol'] = (df['Volume'] > 1.5 * df['AvgVolume20']) & (df['Spread'] > df['Avg_Spread_20']) & (df['Close'] >= df['Low'] + 0.7 * df['Spread'])
    df['Shakeout'] = (df['Low'] < df['Low'].shift(1)) & (df['Close'] > df['Low'] + 0.5 * df['Spread']) & (df['Volume'] > df['AvgVolume20'])
    df['No_Supply'] = (df['Close'] < df['Open']) & (df['Volume'] < df['AvgVolume20']) & (df['Spread'] < df['Avg_Spread_20'])
    df['Test_Supply'] = (df['Close'] < df['Open']) & (df['Spread'] < df['Avg_Spread_20']) & (df['Volume'] < df['Volume'].shift(1)) & (df['Volume'] < df['Volume'].shift(2))
    
    def _eval_day(idx):
        if len(df) < abs(idx) + 5: return None
        
        last = df.iloc[idx]
        prev = df.iloc[idx - 1]
        
        close = last['Close']
        open_c = last['Open']
        vol = last['Volume']
        
        kijun = last['Kijun']
        tenkan = last['Tenkan']
        kijun_prev = prev['Kijun']
        tenkan_prev = prev['Tenkan']
        
        cloud_top = last['CloudTop']
        cloud_top_prev = prev['CloudTop']
        
        avg_vol20 = last['AvgVolume20']
        
        ma10, ma20, ma50, ma100 = last['MA10'], last['MA20'], last['MA50'], last['MA100']
        ma20_prev, ma50_prev = prev['MA20'], prev['MA50']
        
        # --- 1. EARLY BUY (OR) ---
        ichi_early = (close > kijun) and (tenkan > kijun) and (tenkan_prev <= kijun_prev)
        vsa_early = last['Stopping_Vol'] or last['Shakeout'] or last['Test_Supply']
        
        # MUA SỚM THEO MA
        ma_early_hammer = (close - last['Low']) >= 0.6 * (last['High'] - last['Low'])
        ma_early_engulfing = (close > open_c) and (prev['Close'] < prev['Open']) and (close >= prev['Open']) and (open_c <= prev['Close'])
        ma_early_price = ma_early_hammer or ma_early_engulfing
        
        recent_low = df['Low'].iloc[idx-5:idx].min() if len(df) >= abs(idx)+5 else last['Low']
        past_low = df['Low'].iloc[idx-10:idx-5].min() if len(df) >= abs(idx)+10 else recent_low
        ma_early_hl = recent_low >= (past_low * 0.98) # Không phá đáy sâu
        
        ma_early_vol = (prev['Volume'] < avg_vol20) and (vol > prev['Volume'])
        ma_early_ma = ((close > ma10) or (close > ma20)) and (ma10 > prev['MA10'])
        
        ma_early_cond = ma_early_price and ma_early_hl and ma_early_vol and ma_early_ma
        
        is_early = ichi_early or vsa_early or ma_early_cond
        
        # --- 2. ADD 1 (OR) ---
        ichi_conf = (close > kijun) and (tenkan > kijun)
        vsa_conf = (close > open_c) and (vol > avg_vol20)
        ma_conf = ((close > ma20) or (close > ma50)) and ((ma20 > ma20_prev) or (ma50 > ma50_prev))
        
        # MUA GIA TĂNG 1 THEO MA
        high_10 = df['High'].iloc[idx-10:idx].max() if len(df) >= abs(idx)+10 else last['High']
        ma_add1_break = (close > high_10) and (vol > avg_vol20)
        ma_add1_ma = (close > ma10) and (close > ma20) and (ma10 > ma20)
        ma_add1_cond = ma_add1_break and ma_add1_ma
        
        is_add1 = ichi_conf or vsa_conf or ma_conf or ma_add1_cond
        
        # --- 3. ADD 2 (AND) ---
        ha_red_to_green = (prev['HA_Color'] == 'Red') and (last['HA_Color'] == 'Green')
        is_add2 = (close > cloud_top) and (tenkan > kijun) and ha_red_to_green
        
        # --- 4. STRONG BUY (OR) ---
        slice_start = idx - 5
        slice_end = idx if idx != -1 else None 
        # Actually idx=-1 means current. If we want prev 5 bars ending at prev:
        # idx is current. Prev bars are idx-5 to idx-1.
        if idx == -1:
            prev_slice = slice(-6, -1)
        else:
            prev_slice = slice(idx - 5, idx)
        
        has_test_supply_before = df['Test_Supply'].iloc[prev_slice].any()
        vsa_strong = has_test_supply_before and (close > open_c) and (vol > 1.5 * avg_vol20)
        
        ichi_breakout = (prev['Close'] <= cloud_top_prev) and (close > cloud_top)
        
        ma_ordered = (ma10 > ma20) and (ma20 > ma50) and (ma50 > ma100)
        touch_ma10 = (abs(close - ma10) / ma10 < 0.02) if ma10 > 0 else False
        touch_ma20 = (abs(close - ma20) / ma20 < 0.02) if ma20 > 0 else False
        ma_pullback = ma_ordered and (touch_ma10 or touch_ma20) and (close > open_c)
        
        # MUA MẠNH THEO MA
        high_20 = df['High'].iloc[idx-20:idx].max() if len(df) >= abs(idx)+20 else last['High']
        ma_strong_break = (close > high_20)
        ma_strong_ma = ma_ordered and (ma100 > last['MA200'])
        ma_strong_fomo = (close - ma20) / ma20 <= 0.08
        ma_strong_vol = vol >= 1.5 * avg_vol20
        ma_strong_buy = ma_strong_break and ma_strong_ma and ma_strong_fomo and ma_strong_vol
        
        is_strong = vsa_strong or ichi_breakout or ma_pullback or ma_strong_buy
        
        entries = []
        if is_strong: entries.append({"type": "STRONG", "confidence": "MẠNH", "size": "50%", "priority": 4})
        if is_add2: entries.append({"type": "ADD_2", "confidence": "GIA TĂNG 2", "size": "30%", "priority": 3})
        if is_add1: entries.append({"type": "ADD_1", "confidence": "GIA TĂNG 1", "size": "30%", "priority": 2})
        if is_early: entries.append({"type": "EARLY", "confidence": "MUA SỚM", "size": "20%", "priority": 1})
        
        if entries:
            best = max(entries, key=lambda x: x["priority"])
            return best
        return None

    # T-0
    res_today = _eval_day(-1)
    if res_today:
        return {
            "entry_type": res_today["type"],
            "confidence": res_today["confidence"],
            "position_size": res_today["size"],
            "risk_flags": []
        }
        
    # T-1
    res_yest = _eval_day(-2)
    if res_yest:
        return {
            "entry_type": res_yest["type"],
            "confidence": res_yest["confidence"],
            "position_size": res_yest["size"],
            "risk_flags": ["Tín hiệu từ phiên Hôm Qua (T-1)"]
        }
        
    return {"entry_type": "NONE", "confidence": "NONE", "position_size": "0%", "risk_flags": []}
