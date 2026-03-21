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
    last_next = df.iloc[idx+1] if (idx + 1) < 0 or (idx + 1 < len(df)) else last # Handle edge cases if next candle doesn't exist yet, but in reality idx is usually -1 or -2
    
    vol = last['Volume']
    avg_vol20 = last['AvgVolume20']
    spread = last['High'] - last['Low']
    avg_spread20 = df['High'].iloc[idx-20:idx].mean() - df['Low'].iloc[idx-20:idx].mean() if len(df) >= abs(idx)+20 else df['Spread'].mean()
    
    # 1. STOPPING VOLUME / SELLING CLIMAX
    stopping = (vol > 1.5 * avg_vol20) and \
               (spread > avg_spread20) and \
               (last['Close'] > last['Low'] + 0.3 * spread) and \
               (last['Close'] >= prev['Close'] * 0.99) # slightly down or up
               
    # 2. NO SUPPLY
    # small down bar: close < open AND close < previous close
    is_down_bar = (last['Close'] < last['Open']) and (last['Close'] < prev['Close'])
    # next candle close > current close (confirmation). If next candle not available, assume true for scan purposes, or false? Let's assume true if we are at the edge.
    try:
        if idx == -1 or idx == len(df) - 1:
            confirmation = True  # Can't check next candle
        else:
            confirmation = df.iloc[idx+1]['Close'] > last['Close']
    except:
        confirmation = True

    no_supply = (vol < 0.7 * avg_vol20) and \
                (spread < avg_spread20) and \
                is_down_bar and \
                confirmation
                
    # 3. TEST SUPPLY
    recent_low = df['Low'].iloc[idx-10:idx].min() if len(df) >= abs(idx)+10 else df['Low'].min()
    near_recent_low = last['Low'] <= recent_low * 1.02 # within 2% of recent low
    small_spread = spread < avg_spread20 * 0.8
    # close in middle or upper range: close > low + 0.4 * spread
    close_mid_upper = last['Close'] > (last['Low'] + 0.4 * spread)
    
    test_supply = near_recent_low and \
                  (vol < avg_vol20) and \
                  small_spread and \
                  close_mid_upper
    
    return {"stopping": stopping, "no_supply": no_supply, "test_supply": test_supply}

# --- SIGNAL MODULES ---
def _check_add1_strict(df, idx):
    """Refined Add1: Requires EarlyBuy (logic only) in last 30 periods."""
    found_early = False
    for i in range(1, 31):
        if idx - i < 0: break
        if _check_early_buy_logic_only(df, idx - i):
            found_early = True
            break
    if not found_early: return False
    
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    ma10 = last['MA10']
    ma20 = last['MA20']
    ma50 = last['MA50']
    p_ma20 = prev['MA20']
    p_ma50 = prev['MA50']
    
    # --- MA Logic ---
    # TH1: Pullback về MA20
    # uptrend rõ: ma20 > ma50
    uptrend_ma = ma20 > ma50
    # Giá điều chỉnh về gần MA20 (chạm MA20)
    touch_ma20 = last['Low'] <= ma20 * 1.01
    # nến xanh (hoặc rút chân/engulfing) và khối lượng tăng lại. 
    # Đơn giản hóa: nến xanh (close > open) và volume tăng
    green_candle = last['Close'] > last['Open']
    vol_up = last['Volume'] > prev['Volume']
    # Không gia tăng khi rớt xuyên MA20 vol lớn hoặc MA20 đi ngang/xuống
    bad_drop = (last['Close'] < ma20 * 0.98) and (last['Volume'] > last['AvgVolume20'])
    ma20_flat_down = ma20 <= p_ma20
    
    ma_pullback = uptrend_ma and touch_ma20 and green_candle and vol_up and not bad_drop and not ma20_flat_down

    # TH2: MA20 cắt lên MA50 với khối lượng gia tăng, MA10 đang dốc lên
    ma_cross = (prev['MA20'] <= prev['MA50']) and (ma20 > ma50) and (last['Volume'] > last['AvgVolume20']) and (ma10 > prev['MA10'])
    
    ma_add1 = ma_pullback or ma_cross

    # --- Ichimoku Logic ---
    tk = last['Tenkan']
    kj = last['Kijun']
    p_tk = prev['Tenkan']
    p_kj = prev['Kijun']
    k65 = last['Kijun65']
    cloud_top = last['CloudTop']
    cloud_bottom = min(last['SpanA'], last['SpanB'])
    
    price_below_cloud = last['Close'] < cloud_bottom
    price_above_cloud = last['Close'] > cloud_top
    
    tk_cross_kj = (p_tk <= p_kj) and (tk > kj)
    
    # Nếu giá nằm dưới mây, điểm mua gia tăng là khi tenkan cắt lên kijun
    ichi_below_cloud = price_below_cloud and tk_cross_kj
    
    # Nếu giá nằm trên mây: tenkan cắt lên kijun, HOẶC giá điều chỉnh giảm về gần kijun vol nhỏ rồi bật tăng, HOẶC về gần k65 vol nhỏ bật tăng
    near_kj_bounce = (last['Low'] <= kj * 1.02) and (last['Volume'] < last['AvgVolume20']) and green_candle
    near_k65_bounce = (last['Low'] <= k65 * 1.02) and (last['Volume'] < last['AvgVolume20']) and green_candle
    
    ichi_above_cloud = price_above_cloud and (tk_cross_kj or near_kj_bounce or near_k65_bounce)
    
    ichi_add1 = ichi_below_cloud or ichi_above_cloud

    if ma_pullback: return "MA_PULLBACK"
    if ma_cross: return "MA_CROSS"
    if ichi_add1: return "ICHIMOKU"
    
    return False

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
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    ma10 = last['MA10']
    ma20 = last['MA20']
    p_ma10 = prev['MA10']
    
    # --- MA Logic ---
    # giá giảm và khối lượng giảm dần (vol_down)
    vol_down = df['Volume'].iloc[idx-10:idx-2].mean() < df['Volume'].iloc[idx-30:idx-10].mean() if len(df) >= abs(idx)+30 else True
    # MA10 đang dốc lên
    ma10_up = ma10 > p_ma10
    # MA10 cắt lên MA20 hoặc giá cắt lên trên MA10
    ma10_cross_ma20 = (prev['MA10'] <= prev['MA20']) and (ma10 > ma20)
    price_cross_ma10 = (prev['Close'] <= prev['MA10']) and (last['Close'] > ma10)
    
    ma_buy = vol_down and ma10_up and (ma10_cross_ma20 or price_cross_ma10)
    
    # --- Ichimoku Logic ---
    tk = last['Tenkan']
    kj = last['Kijun']
    k65 = last['Kijun65']
    p_tk = prev['Tenkan']
    p_kj = prev['Kijun']
    cloud_top = last['CloudTop']
    cloud_bottom = min(last['SpanA'], last['SpanB'])
    
    price_below_cloud = last['Close'] < cloud_bottom
    price_above_cloud = last['Close'] > cloud_top
    
    tk_cross_kj = (p_tk <= p_kj) and (tk > kj)
    price_cross_tk = (prev['Close'] <= p_tk) and (last['Close'] > tk)
    tk_up = tk > p_tk
    
    # Nếu giá nằm dưới mây, tenkan < kijun và giá cắt lên trên tenkan, tenkan đang dốc lên HOẶC tenkan cắt lên kijun
    ichi_below_cloud = price_below_cloud and (tk < kj) and (price_cross_tk and tk_up) or tk_cross_kj
    
    # Nếu giá nằm trên mây, giá về gần dao 65 với khối lượng giảm dần và bật tăng
    near_k65 = (last['Low'] <= k65 * 1.03) and (last['Low'] >= k65 * 0.98)
    bounce_k65 = price_above_cloud and near_k65 and vol_down and (last['Close'] > prev['Close'])
    
    ichi_buy = ichi_below_cloud or bounce_k65
    
    # --- VSA Logic ---
    vsa = get_vsa_signals(df, idx)
    vsa_buy = vsa['stopping'] or vsa['no_supply'] or vsa['test_supply']
    
    if ma_buy: return "MA"
    if ichi_buy: return "ICHIMOKU"
    if vsa_buy: return "VSA"
    
    return False

def check_add2(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    tk = last['Tenkan']
    kj = last['Kijun']
    cloud_top = last['CloudTop']
    cloud_bottom = min(last['SpanA'], last['SpanB'])
    
    price_above_cloud = last['Close'] > cloud_top
    tk_above_cloud = tk > cloud_top
    kj_above_cloud = kj > cloud_top
    
    # Điều kiện chung: Giá, Tenkan, Kijun đều nằm trên mây
    if not (price_above_cloud and tk_above_cloud and kj_above_cloud):
        return False
        
    ha_color = last['HA_Color']
    prev_ha_color = prev['HA_Color']
    
    # TH1: Nếu tenkan > kijun, điểm mua là khi heikin chuyển từ đỏ sang xanh
    case1 = (tk > kj) and (prev_ha_color == 'Red') and (ha_color == 'Green')
    
    # TH2: Nếu tenkan < kijun, điểm mua là khi heikin vẫn là màu xanh, tenkan cắt lên kijun
    tk_cross_up = (prev['Tenkan'] <= prev['Kijun']) and (tk > kj)
    case2 = (tk < kj) and (ha_color == 'Green') and tk_cross_up
    
    if case1 or case2: return "ICHIMOKU"
    return False

def check_strong_buy(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    ma10, ma20, ma50, ma100 = last['MA10'], last['MA20'], last['MA50'], last['MA100']
    
    # --- Mua mạnh theo MA ---
    # MA10 > ma20 > ma50 > ma100
    perfect_trend = (ma10 > ma20 > ma50 > ma100)
    # giá giảm với khối lượng nhỏ về test MA10 hoặc MA20
    test_ma10_20 = (last['Low'] <= ma10 * 1.01 or last['Low'] <= ma20 * 1.01)
    vol_small = last['Volume'] < last['AvgVolume20']
    green_candle = last['Close'] > last['Open']
    
    ma_strong = perfect_trend and test_ma10_20 and vol_small and green_candle

    # --- Mua mạnh theo Ichimoku ---
    tk = last['Tenkan']
    kj = last['Kijun']
    cloud_top = last['CloudTop']
    cloud_bottom = min(last['SpanA'], last['SpanB'])
    p_cloud_top = prev['CloudTop']
    
    # 1. Breakout Kumo (mây) – tín hiệu mạnh nhất: Giá từ dưới break lên trên mây.
    price_break_cloud = (prev['Close'] <= p_cloud_top) and (last['Close'] > cloud_top)
    # Nến breakout: Thân dài (Close > Open mạnh), Vol tăng mạnh
    body_size = last['Close'] - last['Open']
    avg_body = df['Close'].iloc[idx-20:idx].mean() - df['Open'].iloc[idx-20:idx].mean() if len(df) >= abs(idx)+20 else df['Spread'].mean()
    long_body = body_size > abs(avg_body) # Rough proxy for long body
    high_vol = last['Volume'] > 1.5 * last['AvgVolume20']
    case1_ichi = price_break_cloud and long_body and high_vol
    
    # 2. Chikou Span breakout: Chikou cắt lên giá quá khứ và mây (ở phiên 26)
    # Chikou hiện tại chính là Close hiện tại. Giá quá khứ là Close ở -26. Mây ở -26.
    if len(df) >= abs(idx) + 26 + 1:
        past_idx = idx - 26
        past_close = df['Close'].iloc[past_idx]
        past_prev_close = df['Close'].iloc[past_idx - 1]
        past_cloud_top = df['CloudTop'].iloc[past_idx]
        past_prev_cloud_top = df['CloudTop'].iloc[past_idx - 1]
        
        # Chikou cắt lên giá quá khứ (ở phiên 26 trước đó)
        chikou_cross_price = (prev['Close'] <= past_prev_close) and (last['Close'] > past_close)
        # Chikou cắt lên mây quá khứ
        chikou_cross_cloud = (prev['Close'] <= past_prev_cloud_top) and (last['Close'] > past_cloud_top)
        
        case2_ichi = chikou_cross_price and chikou_cross_cloud
    else:
        case2_ichi = False
        
    # 3. Kumo Twist + Break
    # Mây tương lai (hiện tại + 26) chuyển từ đỏ sang xanh
    # Tức là SpanA tương lai cắt lên SpanB tương lai. 
    # Nhưng trong df, SpanA và SpanB đã được shift 26, nên "hiện tại" của df['SpanA'] chính là đám mây cách đây 26 phiên.
    # Để kiểm tra mây phía trước (mây tương lai), ta phải dùng Tenkan/Kijun hiện tại.
    future_spanA = (tk + kj) / 2
    # future_spanB cần High/Low của 52 phiên tính đến hiện tại.
    high52 = df['High'].iloc[idx-52:idx].max() if len(df) >= abs(idx)+52 else df['High'].max()
    low52 = df['Low'].iloc[idx-52:idx].min() if len(df) >= abs(idx)+52 else df['Low'].min()
    future_spanB = (high52 + low52) / 2
    
    prev_future_spanA = (prev['Tenkan'] + prev['Kijun']) / 2
    # prev_future_spanB proxy using similar logical bound
    prev_high52 = df['High'].iloc[idx-53:idx-1].max() if len(df) >= abs(idx)+53 else high52
    prev_low52 = df['Low'].iloc[idx-53:idx-1].min() if len(df) >= abs(idx)+53 else low52
    prev_future_spanB = (prev_high52 + prev_low52) / 2
    
    kumo_twist = (prev_future_spanA <= prev_future_spanB) and (future_spanA > future_spanB)
    case3_ichi = kumo_twist and (last['Close'] > cloud_top)
    
    # 4. Trạng thái tối thượng: Strong Trend Confirmation
    # Giá > mây, Tenkan > Kijun, Chikou > giá quá khứ, Mây phía trước xanh
    price_gt_cloud = last['Close'] > cloud_top
    tk_gt_kj = tk > kj
    chikou_gt_price = last['Close'] > df['Close'].iloc[idx-26] if len(df) >= abs(idx)+26 else True
    future_cloud_green = future_spanA > future_spanB
    
    case4_ichi = price_gt_cloud and tk_gt_kj and chikou_gt_price and future_cloud_green
    
    ichi_strong = case1_ichi or case2_ichi or case3_ichi or case4_ichi
    
    if ma_strong: return "MA"
    if ichi_strong: return "ICHIMOKU"
    return False

def _eval_day_raw(df: pd.DataFrame, idx: int):
    """Raw signal evaluator for historical scanning (Deduplicated)."""
    r_strong = check_strong_buy(df, idx)
    if r_strong: return {"type": "STRONG", "source": r_strong}
    
    r_add2 = check_add2(df, idx)
    if r_add2: return {"type": "ADD_2", "source": r_add2}
    
    r_add1 = _check_add1_strict(df, idx)
    if r_add1: return {"type": "ADD_1", "source": r_add1}
    
    r_early = _check_early_buy_logic_only(df, idx)
    if r_early: return {"type": "EARLY", "source": r_early}
    
    return None

def _eval_day(df: pd.DataFrame, idx: int):
    """Full AIC evaluator with Prerequisites (Deduplicated)."""
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
    # VSA Rules
    # Note: These are kept for compatibility if other parts of the code use them directly, 
    # but the primary engine uses `get_vsa_signals`. We will update them to match roughly.
    if 'Stopping_Vol' not in df.columns:
        df['Stopping_Vol'] = (df['Volume'] > 1.5 * df['AvgVolume20']) & (df['Spread'] > df['Avg_Spread_20']) & (df['Close'] > df['Low'] + 0.3 * df['Spread'])
    if 'No_Supply' not in df.columns:
        df['No_Supply'] = (df['Volume'] < 0.7 * df['AvgVolume20']) & (df['Spread'] < df['Avg_Spread_20']) & (df['Close'] < df['Open'])
    if 'Test_Supply' not in df.columns:
        df['Test_Supply'] = (df['Volume'] < df['AvgVolume20']) & (df['Spread'] < df['Avg_Spread_20'] * 0.8) & (df['Close'] > df['Low'] + 0.4 * df['Spread'])
    
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
