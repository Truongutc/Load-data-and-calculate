"""
Module 8 – Single Stock Analyzer
==================================
Runs the full TINVEST pipeline on a single ticker and produces a conversational, actionable report.
"""

import logging
import pandas as pd

from .ichimoku_engine import analyze_ichimoku
from .vsa_engine       import analyze_vsa
from .ma_engine        import analyze_ma_trend
from .advanced_entry   import classify_entry
from .accumulation_engine import analyze_accumulation
from .valuation_engine import evaluate_stock_valuation
from .data_loader import enrich_dataframe

logger = logging.getLogger(__name__)


def analyze_stock(ticker: str, df: pd.DataFrame) -> dict:
    logger.info(f"Analyzing {ticker} ...")
    
    # 1. Enrich data 1 lần duy nhất (tất cả MA, ATR, Ichimoku, HA, VSA)
    df_rich = enrich_dataframe(df.copy())
    
    # 2. Call engines — đọc từ columns đã có sẵn, không tính lại
    ichi = analyze_ichimoku(df_rich)
    vsa = analyze_vsa(df_rich)
    ma_trend = analyze_ma_trend(df_rich)
    adv = classify_entry(df_rich)
    accum = analyze_accumulation(df_rich)
    
    last = df_rich.iloc[-1]
    
    # 3. Valuation & Risk Management (AIC Style)
    valuation = evaluate_stock_valuation(ticker, df_rich, adv)
    
    # Store close_26 for Chikou analysis in report
    close_26 = df_rich['Close'].iloc[-26] if len(df_rich) > 26 else df_rich['Close'].iloc[0]

    return {
        "ticker": ticker.upper(),
        "price": float(last["Close"]),
        "date": str(last["Date"].date()) if hasattr(last["Date"], "date") else str(last["Date"]),
        "ichi": ichi,
        "vsa": vsa,
        "ma_trend": ma_trend,
        "adv": adv,
        "accum": accum,
        "valuation": valuation,
        "close_26": float(close_26),
        "ma20": float(df_rich['MA20'].iloc[-1]),
        "ma50": float(df_rich['MA50'].iloc[-1])
    }


def format_report(result: dict) -> str:
    """Format the cumulative results into a professional AIC code report."""
    if not result:
        return "Lỗi: Không có dữ liệu phân tích."

    t = result["ticker"]
    price = result["price"]
    date = result["date"]
    val = result.get("valuation", {})
    adv = result.get("adv", {})
    ichi = result.get("ichi", {})
    ma_trend = result.get("ma_trend", {})
    tech = val.get("tech_health", {})
    
    # Extract valuation data
    s1, s2 = val.get("s1", 0), val.get("s2", 0)
    r1, r2 = val.get("r1", 0), val.get("r2", 0)
    tp1, tp2 = val.get("tp1", 0), val.get("tp2", 0)
    sl1, sl2 = val.get("cutloss_partial", 0), val.get("cutloss_full", 0)
    ts = val.get("trailing_stop", 0)
    bb = val.get("break_buy", 0)
    rs = val.get("risk_score", 0)
    rd = val.get("risk_desc", "N/A")
    rr = val.get("rr_ratio", 0)
    action = val.get("action", "WAIT")
    state = val.get("state", "UNKNOWN")

    sep = "=" * 70
    sep2 = "-" * 70

    lines = [
        "",
        sep,
        f"  💎 AIC code = AI + cơm! 💎 BÁO CÁO PHÂN TÍCH TỔNG HỢP: {t}",
        f"  Ngày: {date}  |  Giá: {price:,.2f}",
        sep,
        ""
    ]

    # --- 1. PHÂN TÍCH INDICATOR (GIẢI THÍCH BẮT BUỘC) ---
    lines.append("  [1. PHÂN TÍCH INDICATOR - GIẢI THÍCH KỸ THUẬT]")
    
    # MA Explanation
    ma_state = "Tích cực (Giá > MA20)" if price >= result.get("ma20", 0) else "Tiêu cực (Giá < MA20)"
    lines.append(f"  ● Moving Average: {ma_state}")
    lines.append("    - Ý nghĩa: MA20 là 'sợi dây sinh mệnh'. Giá trên MA20 là xu hướng ngắn hạn tăng.")
    if ma_trend.get("is_perfect_uptrend"):
        lines.append("    - Cấu trúc: MA10 > 20 > 50 > 100 (Perfect Trend) - Dòng tiền đang vào rất mạnh.")
    
    # Ichimoku Explanation
    tenkan, kijun = ichi.get("tenkan", 0), ichi.get("kijun", 0)
    tk_label = "Tích cực (Tenkan > Kijun)" if tenkan >= kijun else "Yếu (Tenkan < Kijun)"
    if ichi.get("tenkan_kijun_cross") == 'bullish': 
        tk_label = "BÙNG NỔ (Vừa Giao cắt Vàng T-K)"
        
    kumo_pos = "Uptrend (Trên mây)" if ichi.get("price_vs_kumo") == 'above' else ("Sideway (Trong mây)" if ichi.get("price_vs_kumo") == 'inside' else "Downtrend (Dưới mây)")
    lines.append(f"  ● Ichimoku: {kumo_pos} | Momentum: {tk_label}")
    lines.append(f"    - Chi tiết: Tenkan ({tenkan:,.2f}) | Kijun ({kijun:,.2f})")
    lines.append("    - Ý nghĩa: Tenkan/Kijun thể hiện xung lực. Giá trên mây xác nhận chu kỳ tăng dài hạn.")
    
    # Chikou Explanation
    chikou_status = "Thông thoáng (Clear)" if price > result.get("close_26", 0) else "Bị cản (Blocked)"
    lines.append(f"  ● Chikou Span: {chikou_status}")
    lines.append("    - Ý nghĩa: Chikou không bị giá quá khứ cản sẽ giúp trend 'sạch', ít rung lắc.")

    # Kijun65 Explanation
    k65 = val.get("details", {}).get("k65", 0)
    k65_status = "Khỏe (Giá > Kijun65)" if price > k65 else "Rủi ro (Giá < Kijun65)"
    lines.append(f"  ● Dao Găm 65: {k65_status} ({k65:,.2f})")
    lines.append("    - Ý nghĩa: Là mức hỗ trợ/kháng cự tâm lý trung hạn cực kỳ quan trọng.")
    lines.append("")

    # --- 1.1 HỆ THỐNG ĐÁNH GIÁ SỨC MẠNH KỸ THUẬT (NEW) ---
    if tech:
        lines.append("  [1.1 HỆ THỐNG ĐÁNH GIÁ SỨC MẠNH KỸ THUẬT]")
        lines.append(f"  ● Tổng quan sức khỏe : {tech.get('health_rating', 'BÌNH THƯỜNG')}")
        lines.append(f"  ● Chỉ báo ADX        : {tech.get('adx_label', 'N/A')}")
        lines.append(f"  ● Chỉ báo RSI        : {tech.get('rsi_label', 'N/A')}")
        lines.append(f"  ● Chỉ báo MACD       : {tech.get('macd_label', 'N/A')}")
        lines.append("    - Ý nghĩa: ADX đo lực xu hướng, RSI đo xung lực momentum, MACD đo hướng đi dòng tiền.")
        lines.append("")

    # --- 2. XÁC ĐỊNH TRẠNG THÁI CỔ PHIẾU ---
    lines.append("  [2. XÁC ĐỊNH TRẠNG THÁI CỔ PHIẾU]")
    lines.append(f"  ● Trạng thái : {state.replace('_', ' ')}")
    lines.append(f"  ● Vùng giá   : {val.get('position', 'N/A')}")
    state_desc = {
        "STRONG_UPTREND": "Dòng tiền áp đảo, xu hướng và xung lực đều chuẩn mức.",
        "UPTREND": "Uptrend sóng ngắn, đang hướng lên nhưng cần tích lũy thêm.",
        "SIDEWAY": "Giá đang tích lũy hoặc kịp giữa các vùng EMA/Cloud.",
        "DOWNTREND": "Rơi tự do, mọi chỉ báo đều gãy, rủi ro cực cao."
    }
    lines.append(f"  ● Nhận định  : {state_desc.get(state, 'Chưa xác định rõ xu hướng.')}")
    lines.append("")

    # --- 2.1 TÍCH LŨY NỀN (ACCUMULATION) ---
    accum = result.get("accum", {})
    if accum.get("is_accumulation"):
        lines.append("  [2.1 TÍCH LŨY NỀN - CONSOLIDATION]")
        lines.append(f"  ● Trạng thái : ĐANG TÍCH LŨY ({accum.get('base_quality', 'MEDIUM')})")
        if accum.get("notes"):
            lines.append(f"  ● Ghi chú    : {', '.join(accum['notes'])}")
        if accum.get("ready_to_break"):
            lines.append("  ★ CẢNH BÁO : Nền siết chặt, sẵn sàng bùng nổ (Breakout Ready)!")
        lines.append("")

    # --- 3. MỨC GIÁ QUAN TRỌNG ---
    lines.append("  [3. MỨC GIÁ QUAN TRỌNG - S/R]")
    lines.append(f"  ● Giá hiện tại: {price:,.2f}")
    lines.append(f"  ● Hỗ trợ (S): S1: {s1:,.2f} | S2: {s2:,.2f}")
    lines.append(f"  ● Kháng cự (R): R1: {r1:,.2f} | R2: {r2:,.2f}")
    lines.append("")

    # --- 4. HÀNH ĐỘNG (ACTIONABLE) ---
    lines.append(sep2)
    lines.append("  [4. HÀNH ĐỘNG - KẾ HOẠCH GIAO DỊCH]")
    lines.append(f"  ● Điểm mua Breakout : {bb:,.2f} (Vượt R1 + 1%)")
    lines.append(f"  ● Chốt lãi 1 (TP1)   : {tp1:,.2f} (Vùng R1 - 2%)")
    lines.append(f"  ● Chốt lãi 2 (TP2)   : {tp2:,.2f} (Vùng R2 - 2%)")
    lines.append(f"  ● Chặn lãi (TS)      : {ts:,.2f} (Cập nhật theo MA20/Tenkan)")
    lines.append(f"  ● Cắt lỗ 1 (SL1)     : {sl1:,.2f} (Thủng S1 - 1%)")
    lines.append(f"  ● Cắt lỗ 2 (SL2)     : {sl2:,.2f} (Thủng S2 - 3%)")
    lines.append("")

    # --- 5. RỦI RO ---
    lines.append("  [5. RỦI RO & QUẢN TRỊ VỐN]")
    lines.append(f"  ● Risk Score : {rs}/100")
    lines.append(f"  ● Đánh giá   : {rd.upper()}")
    lines.append(f"  ● Tỉ lệ R/R   : {rr} (Lợi nhuận: +{val.get('reward_pct', 0)}% / Rủi ro: -{val.get('risk_pct', 0)}%)")
    if val.get("fomo_warning"):
        lines.append("  ⚠️ CẢNH BÁO  : GIÁ ĐANG CÁCH QUÁ XA MA20 (>12%) - FOMO CAO!")
    lines.append("")

    # --- 6. KẾT LUẬN ---
    lines.append(sep2)
    lines.append("  [6. KẾT LUẬN CUỐI CÙNG]")
    lines.append(f"  ● CÓ NÊN THAM GIA: {action.upper()}")
    
    # Reason construction
    reason = f"Cổ phiếu đang {state.replace('_', ' ')}."
    if action.startswith("YES"):
        reason += f" Có điểm mua [{adv.get('entry_type', 'N/A')}] đi kèm tỉ lệ Technical Health [{tech.get('health_rating', 'N/A')}] tốt."
    elif action.startswith("WAIT"):
        reason += " Cần chờ giá điều chỉnh về vùng hỗ trợ hoặc tích lũy thêm để cải thiện R/R và xung lực."
    else:
        reason += " Xu hướng quá yếu hoặc rủi ro cao, không an toàn để giải ngân."
        
    lines.append(f"  ● Lý do          : {reason}")
    lines.append(sep)
    lines.append("")

    return "\n".join(lines)
