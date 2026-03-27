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

def is_doji_or_pinbar(last, avg_spread):
    """Detect clear bottom signals: Doji or Pin bar (Rút chân)."""
    spread = last['High'] - last['Low']
    if spread == 0: return True
    
    body = abs(last['Close'] - last['Open'])
    
    # Doji: Thân nến nhỏ so với toàn bộ nến
    is_doji = body <= 0.15 * spread
    
    # Pin Bar (Rút chân dưới): Bóng nến dưới chiếm ít nhất 60% nến
    lower_shadow = min(last['Open'], last['Close']) - last['Low']
    is_pinbar_bottom = lower_shadow >= 0.6 * spread
    
    # Nến rút chân và đóng cửa ở 1/3 trên
    close_pos = (last['Close'] - last['Low']) / spread
    is_hammer = (close_pos > 0.6) and (lower_shadow > body)

    return is_doji or is_pinbar_bottom or is_hammer

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
    stopping = (vol > 1.4 * avg_vol20) and \
               (spread > 0.8 * avg_spread20) and \
               (last['Close'] > last['Low'] + 0.3 * spread) and \
               (last['Close'] >= prev['Close'] * 0.985)
               
    # Selling Climax: Giảm mạnh + volume cực lớn
    sc = (last['Close'] < prev['Close'] * 0.96) and (vol > 1.8 * avg_vol20)
               
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
    
    return {"stopping": stopping, "no_supply": no_supply, "test_supply": test_supply, "sc": sc}

# --- SIGNAL MODULES ---
def _eval_with_cache(cache_key, func, df, idx):
    if not hasattr(df, 'attrs'): df.attrs = {}
    if cache_key not in df.attrs: df.attrs[cache_key] = {}
    if idx in df.attrs[cache_key]: return df.attrs[cache_key][idx]
    
    res = func(df, idx)
    df.attrs[cache_key][idx] = res
    return res

def _check_add1_strict_impl(df, idx):
    """Refined Add1: Requires EarlyBuy (logic only) in last 30 periods."""
    found_early = False
    for i in range(1, 31):
        actual_pos = idx if idx >= 0 else len(df) + idx
        if actual_pos - i < 0: break
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

    # TH2: MA-Cross tinh chỉnh (New version)
    # 1. Trend stable: Sum(C > MA20 AND C > MA50, 5) >= 4
    check_window = 5
    actual_pos = idx if idx >= 0 else len(df) + idx
    if actual_pos >= check_window - 1:
        df_sub = df.iloc[actual_pos - check_window + 1 : actual_pos + 1]
        cond_trend_stable = ((df_sub['Close'] > df_sub['MA20']) & (df_sub['Close'] > df_sub['MA50'])).sum() >= 4
    else:
        cond_trend_stable = (last['Close'] > ma20) and (last['Close'] > ma50)

    # 2. Not overextended: (C - MA20) <= 1.5 * ATR14
    atr14 = last.get('ATR14', (last['High']-last['Low']) * 1.5) # Fallback if not calc yet
    cond_not_overextended = (last['Close'] - ma20) <= (1.5 * atr14)

    # 3. Volume good
    avg_vol20 = last.get('AvgVolume20', last['Volume'])
    cond_vol_up = last['Volume'] > 1.2 * avg_vol20
    cond_no_blowoff = last['Volume'] < 2.5 * avg_vol20
    
    body = abs(last['Close'] - last['Open'])
    rng = last['High'] - last['Low'] + 1e-10
    cond_no_spike = body <= 0.7 * rng
    
    prev_close = prev['Close']
    cond_no_gap = (last['Open'] - prev_close) / prev_close < 0.03
    
    cond_volume_good = cond_vol_up and cond_no_blowoff and cond_no_spike and cond_no_gap
    
    ma_cross_refined = cond_trend_stable and cond_not_overextended and cond_volume_good
    
    ma_add1 = ma_pullback or ma_cross_refined

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
    if ma_cross_refined: return "MA_CROSS"
    if ichi_add1: return "ICHIMOKU"
    
    return False

def _check_add1_strict(df, idx):
    return _eval_with_cache('add1_strict', _check_add1_strict_impl, df, idx)

def check_add1(df, idx):
    return _check_add1_strict(df, idx)

def _check_no_recent_signals(df, idx):
    """Ensure no advanced signals in the last 20 periods without deep recursion."""
    for i in range(1, 21):
        actual_pos = idx if idx >= 0 else len(df) + idx
        if actual_pos - i < 0: break
        
        test_idx = idx - i
        # Query discrete logics directly to bypass recursive wrapper tree
        if check_strong_buy(df, test_idx) or check_add2(df, test_idx) or _check_add1_strict(df, test_idx):
            return False
            
    return True

def check_early_buy(df, idx):
    if not _check_no_recent_signals(df, idx): return False
    return _check_early_buy_logic_only(df, idx)

def _check_early_buy_logic_only_impl(df, idx):
    """The technical logic for Early Buy (Refined Cases)."""
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    ma10 = last['MA10']
    ma20 = last['MA20']
    p_ma10 = prev['MA10']
    
    # --- MA Logic ---
    # giá giảm và khối lượng giảm dần (vol_down)
    vol_down = df['Volume'].iloc[idx-10:idx-2].mean() < df['Volume'].iloc[idx-30:idx-10].mean() if len(df) >= abs(idx)+30 else True
    # Bổ sung: Giá tạo đáy rõ ràng (doji/rút chân)
    clear_bottom = is_doji_or_pinbar(last, df['High'].iloc[idx-20:idx].mean() - df['Low'].iloc[idx-20:idx].mean())
    
    # MA10 đang dốc lên
    ma10_up = ma10 > p_ma10
    # MA10 cắt lên MA20 hoặc giá cắt lên trên MA10
    ma10_cross_ma20 = (prev['MA10'] <= prev['MA20']) and (ma10 > ma20)
    price_cross_ma10 = (prev['Close'] <= prev['MA10']) and (last['Close'] > ma10)
    
    ma_buy = vol_down and clear_bottom and ma10_up and (ma10_cross_ma20 or price_cross_ma10)
    
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
    ichi_below_cloud = price_below_cloud and (((tk < kj) and price_cross_tk and tk_up) or tk_cross_kj)
    
    # Nếu giá nằm trên mây, giá về gần dao 65 với khối lượng giảm dần và bật tăng
    # Bổ sung: Điều kiện Tenkan < Kijun cho Mua sớm trên mây
    near_k65 = (last['Low'] <= k65 * 1.03) and (last['Low'] >= k65 * 0.98)
    bounce_k65 = price_above_cloud and near_k65 and vol_down and (last['Close'] > prev['Close']) and (tk < kj)
    
    ichi_buy = ichi_below_cloud or bounce_k65
    
    # --- VSA Logic (3-phase Early Buy) ---
    # Phase 1: Có Stopping Volume hoặc Selling Climax trong 20 phiên gần nhất
    has_phase1 = False
    for i in range(0, 21):
        actual_pos = idx if idx >= 0 else len(df) + idx
        if actual_pos - i < 0: break
        vsa_past = get_vsa_signals(df, idx - i)
        if vsa_past['stopping'] or vsa_past['sc']:
            has_phase1 = True
            break
            
    # Phase 2: Xác nhận cạn cung (No Supply / Test Supply) trong 5 phiên gần nhất
    vsa_now = get_vsa_signals(df, idx)
    has_phase2 = vsa_now['no_supply'] or vsa_now['test_supply']
    
    # Phase 3: Test thành công (Không thủng đáy gần nhất)
    recent_low = df['Low'].iloc[idx-10:idx].min() if len(df) >= abs(idx)+10 else df['Low'].min()
    test_success = last['Low'] >= recent_low * 0.99 # Cho phép sai số 1%
    
    vsa_buy = has_phase1 and has_phase2 and test_success
    
    if ma_buy: return "MA"
    if ichi_buy: return "ICHIMOKU"
    if vsa_buy: return "VSA"
    
    return False

def _check_early_buy_logic_only(df, idx):
    return _eval_with_cache('early_logic', _check_early_buy_logic_only_impl, df, idx)

def _check_add2_impl(df, idx):
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
    
    # TH2: Nếu tenkan < kijun (trước đó), điểm mua là khi heikin vẫn là màu xanh, tenkan cắt lên kijun
    tk_cross_up = (prev['Tenkan'] <= prev['Kijun']) and (tk > kj)
    case2 = (ha_color == 'Green') and tk_cross_up
    
    if case1 or case2: return "ICHIMOKU"
    return False

def check_add2(df, idx):
    return _eval_with_cache('add2', _check_add2_impl, df, idx)

def _check_strong_buy_impl(df, idx):
    last = df.iloc[idx]
    prev = df.iloc[idx-1]
    
    ma10, ma20, ma50, ma100, ma200 = last['MA10'], last['MA20'], last['MA50'], last['MA100'], last.get('MA200', 0)
    
    # --- Mua mạnh theo MA ---
    # 1. Cấu trúc xếp hàng: MA10 > ma20 > ma50 > ma100 > ma200
    perfect_trend = (ma10 > ma20 > ma50 > ma100 > ma200)
    
    # 2. Giá không quá xa MA10 (tránh hưng phấn quá đà)
    dist_ma10 = last['Close'] <= ma10 * 1.10
    
    # 3. Điều kiện khối lượng: Vol > AvgVol20 và Vol < 3 * AvgVol20 (không blow-off)
    avg_vol20 = last['AvgVolume20']
    vol_strong = last['Volume'] > avg_vol20
    cond_no_blowoff = last['Volume'] < 3 * avg_vol20
    
    green_candle = last['Close'] > last['Open']
    
    ma_strong = perfect_trend and dist_ma10 and vol_strong and cond_no_blowoff and green_candle

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
    
    ichi_strong = case1_ichi or case2_ichi or case3_ichi
    
    if ma_strong: return "MA"
    if ichi_strong: return "ICHIMOKU"
    return False

def check_strong_buy(df, idx):
    return _eval_with_cache('strong_buy', _check_strong_buy_impl, df, idx)

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
    """Ensure all required columns for signal evaluation are present.
    Delegates to enrich_dataframe() — the single source of truth.
    If columns already exist, this is a near-zero-cost no-op.
    """
    if len(df) < 10: return df
    from .data_loader import enrich_dataframe
    return enrich_dataframe(df)

def classify_entry(df: pd.DataFrame) -> dict:
    if len(df) < 2:
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
