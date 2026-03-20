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

# --- VSA PROXIES ---
def get_vsa_signals(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    vol = last['Volume']
    avg_vol20 = last['AvgVolume20']
    spread = last['High'] - last['Low']
    avg_spread20 = df['High'].iloc[idx-20:idx].mean() - df['Low'].iloc[idx-20:idx].mean() if len(df) >= abs(idx)+20 else spread

    stopping = (vol > 1.5 * avg_vol20) and (last['Close'] >= (last['Low'] + 0.7 * spread))
    shakeout = (last['Low'] < prev['Low']) and (last['Close'] > (last['Low'] + 0.5 * spread)) and (vol > avg_vol20)
    no_supply = (last['Close'] < last['Open']) and (vol < avg_vol20) and (spread < avg_spread20)
    test_supply = (last['Close'] < last['Open']) and (spread < avg_spread20) and (vol < df['Volume'].iloc[idx-1]) and (vol < df['Volume'].iloc[idx-2])
    
    return {"stopping": stopping, "shakeout": shakeout, "no_supply": no_supply, "test_supply": test_supply}

# --- SIGNAL MODULES ---
def _check_add1_logic_only(df, idx):
    """Raw logic for Add1 (without any recursive signal history checks)."""
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    ma20 = last['MA20']
    ma50 = last['MA50']
    
    ma_conf = (last['Close'] > ma20 or last['Close'] > ma50) and (ma20 > df['MA20'].iloc[idx-1] or ma50 > df['MA50'].iloc[idx-1])
    ichi_conf = (last['Close'] > last['Kijun']) and (last['Tenkan'] > last['Kijun'])
    vsa_conf = (last['Close'] > last['Open']) and (last['Volume'] > last['AvgVolume20'])
    k65_conf = last['Close'] > last['Kijun65']
    
    return ma_conf or ichi_conf or vsa_conf or k65_conf

def _check_add1_strict(df, idx):
    """Refined Add1: Requires EarlyBuy (logic only) in last 10 periods."""
    found_early = False
    for i in range(1, 11):
        if idx - i < 0: break
        if _check_early_buy_logic_only(df, idx - i):
            found_early = True
            break
    if not found_early: return False
    return _check_add1_logic_only(df, idx)

def check_add1(df, idx):
    return _check_add1_strict(df, idx)

def _check_no_recent_signals(df, idx):
    """Ensure no advanced signals in the last 20 periods."""
    for i in range(1, 21):
        if idx - i < 0: break
        res = _eval_day_raw(df, idx - i) 
        if res and res["type"] in ["ADD_1", "ADD_2", "STRONG"]:
            return False
    return True

def check_early_buy(df, idx):
    if not _check_no_recent_signals(df, idx): return False
    return _check_early_buy_logic_only(df, idx)

def _check_early_buy_logic_only(df, idx):
    """The technical logic for Early Buy (Refined Cases)."""
    # print(f"--- LOGIC CHECK FOR IDX {idx} ---", flush=True) # Optional debug
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    ma10, ma20, ma50 = last['MA10'], last['MA20'], last['MA50']
    p_ma10, p_ma20 = prev['MA10'], prev['MA20']
    
    # MA Cases
    ll10 = df['Low'].iloc[idx-10:idx].min()
    vol_down = df['Volume'].iloc[idx-10:idx-2].mean() < df['Volume'].iloc[idx-30:idx-10].mean()
    ma_case1 = (ma10 < ma20) and (last['Close'] > ma10) and (ma10 > p_ma10) and (ma20 >= p_ma20) and (last['Low'] <= ll10 * 1.05) and vol_down
    ma_case2 = (ma10 < ma50) and (ma20 < ma50) and (p_ma10 <= p_ma20) and (ma10 > ma20)
    
    # Ichi Cases
    tk, kj, k65 = last['Tenkan'], last['Kijun'], last['Kijun65']
    p_tk, p_kj = prev['Tenkan'], prev['Kijun']
    ichi_case1 = (tk < kj) and (last['Close'] > tk) and (tk > p_tk)
    ichi_case2 = (p_tk <= p_kj) and (tk > kj) and (tk > p_tk)
    above_cloud = last['Close'] > last['CloudTop']
    near_k65 = (last['Low'] <= k65 * 1.03) and (last['Low'] >= k65 * 0.99)
    k65_bounce = above_cloud and near_k65 and (tk > k65) and (kj > k65) and (last['Close'] > prev['Close'])
    
    return ma_case1 or ma_case2 or ichi_case1 or ichi_case2 or k65_bounce

def check_add2(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    if last['Close'] <= last['CloudTop']: return False
    tk_bullish = last['Tenkan'] > last['Kijun']
    ha_shift = (prev['HA_Color'] == 'Red') and (last['HA_Color'] == 'Green')
    ha_green = (last['HA_Color'] == 'Green')
    tk_cross_up = (df['Tenkan'].iloc[idx-1] <= df['Kijun'].iloc[idx-1]) and (last['Tenkan'] > last['Kijun'])
    return (tk_bullish and ha_shift) or (ha_green and tk_cross_up)

def check_strong_buy(df, idx):
    last = df.iloc[idx]
    if last['Close'] <= last['CloudTop']: return False
    ma10, ma20, ma50, ma100 = last['MA10'], last['MA20'], last['MA50'], last['MA100']
    perfect_trend = (ma10 > ma20 > ma50 > ma100) and (ma20 > df['MA20'].iloc[idx-1])
    pullback = (last['Low'] <= ma10 * 1.01 or last['Low'] <= ma20 * 1.01) and (last['Close'] > last['Open'])
    ma_strong = perfect_trend and pullback
    ichi_strong = (last['Tenkan'] > last['Kijun']) and (last['SpanA'] > last['SpanB']) and (last['Close'] > df['Close'].iloc[idx-26] if len(df) > abs(idx)+26 else True)
    test_recently = any([get_vsa_signals(df, idx-i)['test_supply'] for i in range(1, 6)])
    vsa_strong = test_recently and (last['Close'] > last['Open']) and (last['Volume'] > 1.5 * last['AvgVolume20']) and (last['Close'] > ma50)
    return ma_strong or ichi_strong or vsa_strong

def _eval_day_raw(df: pd.DataFrame, idx: int):
    """Raw signal evaluator for historical scanning (Deduplicated)."""
    if check_strong_buy(df, idx): return {"type": "STRONG"}
    if check_add2(df, idx): return {"type": "ADD_2"}
    if _check_add1_strict(df, idx): return {"type": "ADD_1"}
    if _check_early_buy_logic_only(df, idx): return {"type": "EARLY"}
    return None

def _eval_day(df: pd.DataFrame, idx: int):
    """Full AIC evaluator with Prerequisites (Deduplicated)."""
    if len(df) < abs(idx) + 65: return None
    if check_strong_buy(df, idx): return {"type": "STRONG", "confidence": "MẠNH", "size": "50%"}
    if check_add2(df, idx): return {"type": "ADD_2", "confidence": "GIA TĂNG 2", "size": "30%"}
    if check_add1(df, idx): return {"type": "ADD_1", "confidence": "GIA TĂNG 1", "size": "20%"}
    if check_early_buy(df, idx): return {"type": "EARLY", "confidence": "SỚM", "size": "20%"}
    return None

def ensure_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all required columns for signal evaluation are present."""
    if len(df) < 10: return df
    
    # MA
    if 'MA10' not in df.columns: df['MA10'] = df['Close'].rolling(10).mean()
    if 'MA20' not in df.columns: df['MA20'] = df['Close'].rolling(20).mean()
    if 'MA50' not in df.columns: df['MA50'] = df['Close'].rolling(50).mean()
    if 'MA100' not in df.columns: df['MA100'] = df['Close'].rolling(100).mean()
    if 'MA200' not in df.columns: df['MA200'] = df['Close'].rolling(200).mean()
    
    # Ichimoku
    if 'Tenkan' not in df.columns:
        df['Tenkan'] = (df['High'].rolling(9).max() + df['Low'].rolling(9).min()) / 2
    if 'Kijun' not in df.columns:
        df['Kijun'] = (df['High'].rolling(26).max() + df['Low'].rolling(26).min()) / 2
    if 'Kijun65' not in df.columns:
        df['Kijun65'] = (df['High'].rolling(65).max() + df['Low'].rolling(65).min()) / 2
    if 'SpanA' not in df.columns:
        df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
    if 'SpanB' not in df.columns:
        df['SpanB'] = ((df['High'].rolling(52).max() + df['Low'].rolling(52).min()) / 2).shift(26)
    if 'CloudTop' not in df.columns:
        df['CloudTop'] = df[['SpanA', 'SpanB']].max(axis=1)
    
    # Heikin Ashi
    if 'HA_Color' not in df.columns:
        df_ha = calculate_ha(df)
        df['HA_Open'] = df_ha['HA_Open']
        df['HA_Close'] = df_ha['HA_Close']
        df['HA_Color'] = np.where(df['HA_Close'] > df['HA_Open'], 'Green', 'Red')
    
    # VSA Proxy
    if 'AvgVolume20' not in df.columns: df['AvgVolume20'] = df['Volume'].rolling(20).mean()
    if 'Spread' not in df.columns: df['Spread'] = df['High'] - df['Low']
    if 'Avg_Spread_20' not in df.columns: df['Avg_Spread_20'] = df['Spread'].rolling(20).mean()
    
    # VSA Rules
    if 'Stopping_Vol' not in df.columns:
        df['Stopping_Vol'] = (df['Volume'] > 1.5 * df['AvgVolume20']) & (df['Spread'] > df['Avg_Spread_20']) & (df['Close'] >= df['Low'] + 0.7 * df['Spread'])
    if 'Shakeout' not in df.columns:
        df['Shakeout'] = (df['Low'] < df['Low'].shift(1)) & (df['Close'] > df['Low'] + 0.5 * df['Spread']) & (df['Volume'] > df['AvgVolume20'])
    if 'No_Supply' not in df.columns:
        df['No_Supply'] = (df['Close'] < df['Open']) & (df['Volume'] < df['AvgVolume20']) & (df['Spread'] < df['Avg_Spread_20'])
    if 'Test_Supply' not in df.columns:
        df['Test_Supply'] = (df['Close'] < df['Open']) & (df['Spread'] < df['Avg_Spread_20']) & (df['Volume'] < df['Volume'].shift(1)) & (df['Volume'] < df['Volume'].shift(2))
    
    return df

def classify_entry(df: pd.DataFrame) -> dict:
    if len(df) < 200:
        return {"entry_type": "NONE", "confidence": "NONE", "position_size": "0%", "details": {}, "risk_flags": []}
        
    df = ensure_indicators(df.copy())
    
    res_today = _eval_day(df, -1)
    if res_today:
        return {
            "entry_type": res_today["type"],
            "confidence": res_today["confidence"],
            "position_size": res_today["size"],
            "details": res_today.get("details", {}),
            "risk_flags": []
        }
    res_yest = _eval_day(df, -2)
    if res_yest:
        return {
            "entry_type": res_yest["type"],
            "confidence": res_yest["confidence"],
            "position_size": res_yest["size"],
            "details": res_yest.get("details", {}),
            "risk_flags": ["Tín hiệu từ phiên Hôm Qua (T-1)"]
        }
    return {"entry_type": "NONE", "confidence": "NONE", "position_size": "0%", "details": {}, "risk_flags": []}

def get_recent_entry_state(df: pd.DataFrame, window: int = 5) -> dict:
    """Identify the most advanced signal in the last 'window' bars."""
    if len(df) < 200:
        return {"state": "NO_SETUP", "entry_price": 0.0}

    df = ensure_indicators(df.copy())

    hierarchy = {"STRONG": 4, "ADD_2": 4, "ADD_1": 3, "EARLY": 2, "NONE": 1}
    state_names = {4: "AFTER_ADD2_STRONG", 3: "AFTER_ADD1", 2: "JUST_EARLY", 1: "NO_SETUP"}

    best_priority = 1
    found_price = 0.0

    for i in range(1, window + 1):
        idx = -i
        res = _eval_day(df, idx)
        if res:
            prio = hierarchy.get(res["type"], 1)
            if prio > best_priority:
                best_priority = prio
                found_price = float(df['Close'].iloc[idx])
            elif prio == best_priority and found_price == 0:
                found_price = float(df['Close'].iloc[idx])

    return {
        "state": state_names[best_priority],
        "entry_price": found_price,
        "buy_zone": found_price
    }
