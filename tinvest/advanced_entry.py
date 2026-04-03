import pandas as pd
import numpy as np

def calculate_ha(df: pd.DataFrame) -> pd.DataFrame:
    df_ha = pd.DataFrame(index=df.index)
    df_ha['HA_Color'] = np.where(df['Close'] >= df['Open'], 'Green', 'Red')
    df_ha['HA_Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    ha_open = np.zeros(len(df))
    ha_open[0] = (df['Open'].iloc[0] + df['Close'].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i-1] + df_ha['HA_Close'].iloc[i-1]) / 2
    df_ha['HA_Open'] = ha_open
    return df_ha

def _get_adx_status(df, idx):
    if len(df) < abs(idx) + 1: return "ORANGE"
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    adx = last['ADX']
    p_adx = prev['ADX']
    di_plus = last['DI_Plus']
    di_minus = last['DI_Minus']
    
    adx_up = adx > p_adx
    di_up = di_plus >= di_minus
    hl_range = adx <= 20
    
    if hl_range: return "ORANGE"
    if adx_up and di_up: return "WHITE"
    if not adx_up and di_up: return "GREEN"
    return "RED"

def is_doji_or_pinbar(last, avg_spread):
    """Detect clear bottom signals: Doji or Pin bar (Rút chân)."""
    spread = last['High'] - last['Low']
    if spread == 0: return True
    body = abs(last['Close'] - last['Open'])
    is_doji = body <= 0.15 * spread
    lower_shadow = min(last['Open'], last['Close']) - last['Low']
    is_pinbar_bottom = lower_shadow >= 0.6 * spread
    close_pos = (last['Close'] - last['Low']) / spread
    is_hammer = (close_pos > 0.6) and (lower_shadow > body)
    return is_doji or is_pinbar_bottom or is_hammer

def get_vsa_signals(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    vol = last['Volume']
    avg_vol20 = last['AvgVolume20']
    spread = last['High'] - last['Low']
    avg_spread20 = df['Spread'].iloc[idx-20:idx].mean() if len(df) >= abs(idx)+20 else df['Spread'].mean()
    
    stopping = (vol > 1.4 * avg_vol20) and (spread > 0.8 * avg_spread20) and (last['Close'] > last['Low'] + 0.3 * spread)
    sc = (last['Close'] < prev['Close'] * 0.96) and (vol > 1.8 * avg_vol20)
    
    is_down_bar = (last['Close'] < last['Open']) and (last['Close'] < prev['Close'])
    no_supply = (vol < 0.7 * avg_vol20) and (spread < avg_spread20) and is_down_bar
                
    test_supply = (vol < avg_vol20) and (spread < avg_spread20 * 0.8) and (last['Close'] > (last['Low'] + 0.4 * spread))
    return {"stopping": stopping, "no_supply": no_supply, "test_supply": test_supply, "sc": sc}

def _eval_with_cache(cache_key, func, df, idx):
    if not hasattr(df, 'attrs'): df.attrs = {}
    if cache_key not in df.attrs: df.attrs[cache_key] = {}
    if idx in df.attrs[cache_key]: return df.attrs[cache_key][idx]
    res = func(df, idx)
    df.attrs[cache_key][idx] = res
    return res

def _check_add1_strict_impl(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    ma10, ma20, ma50 = last['MA10'], last['MA20'], last['MA50']
    adx_status = _get_adx_status(df, idx)
    if adx_status == "ORANGE": return False
    
    case1 = (ma20 > ma50) and (last['Low'] <= ma20 * 1.015) and (last['Close'] > last['Open'])
    case2 = ((prev['MA10'] <= prev['MA20']) and (ma10 > ma20)) or ((prev['MA20'] <= prev['MA50']) and (ma20 > ma50))
    
    tk, kj = last['Tenkan'], last['Kijun']
    above_cloud = last['Close'] > last['CloudTop']
    case3 = above_cloud and ((last['Low'] <= kj * 1.015 and last['Close'] > kj) or (last['Low'] <= last['Kijun65'] * 1.015 and last['Close'] > last['Kijun65']))
    case4 = (last['Close'] < last['CloudTop']) and (prev['Tenkan'] <= prev['Kijun']) and (tk > kj)
    
    if case1: return "MA_PULLBACK"
    if case2: return "MA_CROSS"
    if case3: return "ICHI_BOUNCE"
    if case4: return "ICHI_CROSS"
    return False

def check_add1(df, idx):
    return _eval_with_cache('add1_strict', _check_add1_strict_impl, df, idx)

def _check_no_recent_signals(df, idx):
    for i in range(1, 21):
        actual_pos = idx if idx >= 0 else len(df) + idx
        if actual_pos - i < 0: break
        test_idx = idx - i
        if check_strong_buy(df, test_idx) or check_add2(df, test_idx) or check_add1(df, test_idx):
            return False
    return True

def _check_early_buy_logic_only_impl(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    cross_tk = (prev['Close'] <= prev['Tenkan']) and (last['Close'] > last['Tenkan'])
    cross_ma10 = (prev['Close'] <= prev['MA10']) and (last['Close'] > last['MA10'])
    
    recent_lows = [v for v in df['SwingLow'].iloc[idx-20:idx+1] if v > 0]
    is_higher_low = True
    if len(recent_lows) >= 2:
        is_higher_low = recent_lows[-1] >= recent_lows[-2]
    
    vsa = get_vsa_signals(df, idx)
    if (cross_tk or cross_ma10) and is_higher_low:
        return "VSA_REVERSAL" if (vsa['stopping'] or vsa['test_supply']) else "PRICE_REVERSAL"
    
    if last['ADX'] < 20 and last['RSI'] < 35: return "RSI_BOTTOM"
    return False

def check_early_buy(df, idx):
    if not _check_no_recent_signals(df, idx): return False
    return _eval_with_cache('early_logic', _check_early_buy_logic_only_impl, df, idx)

def _check_add2_impl(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    tk, kj = last['Tenkan'], last['Kijun']
    cloud_top = last['CloudTop']
    if not (last['Close'] > cloud_top and tk > cloud_top and kj > cloud_top): return False
    case1 = (tk >= kj) and (prev['HA_Color'] == 'Red') and (last['HA_Color'] == 'Green')
    case2 = (last['HA_Color'] == 'Green') and (prev['Tenkan'] <= prev['Kijun']) and (tk > kj)
    if case1: return "HA_REVERSAL"
    if case2: return "TK_CROSS_UP"
    return False

def check_add2(df, idx):
    return _eval_with_cache('add2_strict', _check_add2_impl, df, idx)

def _check_strong_buy_impl(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    ma10, ma20, ma50, ma100 = last['MA10'], last['MA20'], last['MA50'], last['MA100']
    ma200 = last.get('MA200', 0)
    
    perfect_stack = (ma10 > ma20 > ma50 > ma100) and (ma100 > ma200)
    case1 = perfect_stack and (last['Low'] <= ma20 * 1.015) and (last['Close'] > ma20)
    
    price_break = (prev['Close'] <= prev['CloudTop']) and (last['Close'] > last['CloudTop'])
    case2 = price_break and (last['Volume'] > 1.2 * last['AvgVolume20']) and (_get_adx_status(df, idx) == "WHITE")
    
    case3 = (last['ADX'] > 25) and (last['MACD_Hist'] > prev['MACD_Hist'] > 0)
    
    if case1: return "PERFECT_MA"
    if case2: return "KUMO_BREAK"
    if case3: return "ADX_COMBO"
    return False

def check_strong_buy(df, idx):
    return _eval_with_cache('strong_buy', _check_strong_buy_impl, df, idx)

def _eval_day(df: pd.DataFrame, idx: int):
    if len(df) < abs(idx) + 65: return None
    r_strong = check_strong_buy(df, idx)
    if r_strong: return {"type": "STRONG", "confidence": "MẠNH", "size": "50%", "details": {"source": r_strong}}
    r_add2 = check_add2(df, idx)
    if r_add2: return {"type": "ADD_2", "confidence": "GIA TĂNG 2", "size": "30%", "details": {"source": r_add2}}
    r_add1 = check_add1(df, idx)
    if r_add1: return {"type": "ADD_1", "confidence": "GIA TĂNG 1", "size": "20%", "details": {"source": r_add1}}
    r_early = check_early_buy(df, idx)
    if r_early: return {"type": "EARLY", "confidence": "SỚM", "size": "20%", "details": {"source": r_early}}
    return None

def ensure_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) < 10: return df
    from .data_loader import enrich_dataframe
    return enrich_dataframe(df)

def classify_entry(df: pd.DataFrame) -> dict:
    if len(df) < 2: return {"entry_type": "NONE", "confidence": "NONE", "position_size": "0%", "details": {}, "risk_flags": []}
    df = ensure_indicators(df.copy())
    res_today = _eval_day(df, -1)
    if res_today:
        return {"entry_type": res_today["type"], "confidence": res_today["confidence"], "position_size": res_today["size"], "details": res_today.get("details", {}), "risk_flags": []}
    res_yest = _eval_day(df, -2)
    if res_yest:
        return {"entry_type": res_yest["type"], "confidence": res_yest["confidence"], "position_size": res_yest["size"], "details": res_yest.get("details", {}), "risk_flags": ["Tín hiệu từ phiên Hôm Qua (T-1)"]}
    return {"entry_type": "NONE", "confidence": "NONE", "position_size": "0%", "details": {}, "risk_flags": []}
