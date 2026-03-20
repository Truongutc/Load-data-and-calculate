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

logger = logging.getLogger(__name__)


def analyze_stock(ticker: str, df: pd.DataFrame) -> dict:
    logger.info(f"Analyzing {ticker} ...")
    
    ichi = analyze_ichimoku(df)
    vsa = analyze_vsa(df)
    ma_trend = analyze_ma_trend(df)
    adv = classify_entry(df)
    accum = analyze_accumulation(df)
    
    last = df.iloc[-1]
    
    ma20 = df['Close'].rolling(20).mean().iloc[-1]
    ma50 = df['Close'].rolling(50).mean().iloc[-1]
    
    return {
        "ticker": ticker.upper(),
        "price": float(last["Close"]),
        "date": str(last["Date"].date()) if hasattr(last["Date"], "date") else str(last["Date"]),
        "ichi": ichi,
        "vsa": vsa,
        "ma_trend": ma_trend,
        "adv": adv,
        "accum": accum,
        "ma20": ma20,
        "ma50": ma50,
        "close": last["Close"]
    }


def format_report(result: dict) -> str:
    """
    Format the output of analyze_stock() as a human-readable conversational text report.
    """
    t = result["ticker"]
    price = result["price"]
    date = result["date"]
    
    ichi = result["ichi"]
    vsa = result["vsa"]
    ma_trend = result["ma_trend"]
    adv = result["adv"]
    accum = result["accum"]
    
    close = result["close"]
    ma20 = result["ma20"]
    ma50 = result["ma50"]
    
    sep  = "═" * 70
    sep2 = "─" * 70
    
    lines = [
        "",
        sep,
        f"  📊  TINVEST – BÁO CÁO PHÂN TÍCH TỔNG HỢP: {t}",
        f"  Ngày: {date}  |  Giá: {price:,.2f}",
        sep,
        ""
    ]
    
    # --- 1. ICHIMOKU ---
    lines.append("  [1. ICHIMOKU - XU HƯỚNG ĐÁM MÂY]")
    kumo_status = "Trên mây" if ichi['price_vs_kumo'] == 'above' else "Dưới mây hoặc Trong mây"
    tk_cross = "Tenkan > Kijun" if ichi['tenkan_kijun_cross'] == 'bullish' else "Tenkan < Kijun"
    
    lines.append(f"  • Vị thế giá : {kumo_status}")
    lines.append(f"  • Động lượng : {tk_cross}")
    
    if ichi['price_vs_kumo'] == 'above' and ichi['tenkan_kijun_cross'] == 'bullish':
        ichi_eval = "MẠNH (Đang trong trend tăng chuẩn Ichimoku)"
    elif ichi['price_vs_kumo'] == 'below':
        ichi_eval = "YẾU (Nằm dưới mây chìm trong downtrend)"
    else:
        ichi_eval = "TRUNG TÍNH (Đang tích lũy hoặc chưa bứt thoát đám mây)"
    lines.append(f"  => Đánh giá chung: Xu hướng Ichimoku hiện tại đang {ichi_eval}.")
    lines.append("")
    
    # --- 2. MOVING AVERAGE ---
    lines.append("  [2. MOVING AVERAGE - HÀNH VI ĐƯỜNG GIÁ]")
    ma20_status = "Giữ được trend ngắn hạn" if close >= ma20 else "Mất MA20 (Rủi ro ngắn hạn)"
    ma50_status = "Giữ được trend trung hạn" if close >= ma50 else "Thủng MA50 (Rủi ro trung hạn)"
    
    lines.append(f"  • Ngắn hạn (MA20): Giá đang {'nằm TRÊN' if close >= ma20 else 'nằm DƯỚI'} MA20 ({ma20_status})")
    lines.append(f"  • Trung hạn (MA50): Giá đang {'nằm TRÊN' if close >= ma50 else 'nằm DƯỚI'} MA50 ({ma50_status})")
    
    if ma_trend['is_perfect_uptrend']:
        lines.append("  • Cấu trúc     : MA10 > MA20 > MA50 > 100 > 200 (Xòe quạt hướng lên)")
        ma_eval = "RẤT MẠNH (Cổ phiếu đang trên đà Siêu Điểm Mua - Siêu Trend)"
    elif close >= ma20 and close >= ma50:
        ma_eval = "TÍCH CỰC (Đang giữ thành công các mốc hỗ trợ quan trọng)"
    elif close < ma20 and close < ma50:
        ma_eval = "TIÊU CỰC (Giá cắm đầu dưới các đường dây trung bình)"
    else:
        ma_eval = "GIẰNG CO (Giá đang kẹp giữa MA20 và MA50)"
    lines.append(f"  => Đánh giá chung: Cấu trúc MA cho thấy cổ phiếu đang {ma_eval}.")
    lines.append("")
    
    # --- 3. VSA & RECENT EFFORT ---
    lines.append("  [3. VSA & PRICE ACTION - DIỄN BIẾN DÒNG TIỀN]")
    vsa_dom = vsa['dominant'].upper()
    vsa_signals = vsa.get("signals", [])
    
    if vsa_signals:
        sig_str = ", ".join([s['type'].replace('_', ' ').title() for s in vsa_signals])
        lines.append(f"  • Các nỗ lực gần đây    : Xuất hiện các cột {sig_str}")
    else:
        lines.append("  • Các nỗ lực gần đây    : Không ghi nhận hành vi đẩy giá / xả hàng bất thường nào.")
        
    if vsa_dom == 'BULLISH':
        vsa_eval = "DÒNG TIỀN ỦNG HỘ TĂNG (Phe mua đang kiểm soát, lực cầu lớn hơn cung)"
    elif vsa_dom == 'BEARISH':
        vsa_eval = "CHỊU ÁP LỰC BÁN (Rủi ro phân phối xả hàng, lực cung lớn hơn cầu)"
    else:
        if accum['is_accumulation']:
            vsa_eval = "CẠN KIỆT ĐI NGANG (Cổ phiếu đang siết nền cực chặt, biên độ hẹp, chờ nổ)"
        else:
            vsa_eval = "CÂN BẰNG (Chưa có dòng tiền lớn khổng lồ nào vào dẫn dắt)"
            
    lines.append(f"  => Đánh giá chung: Trạng thái dòng tiền hiện tại mang tính {vsa_eval}.")
    lines.append("")
    
    # --- 4. KẾT LUẬN & HÀNH ĐỘNG ---
    lines.append(sep2)
    lines.append("  [4. ĐÁNH GIÁ TỔNG QUAN & HÀNH ĐỘNG]")
    
    # Tổng hợp trạng thái
    if ma_trend['is_perfect_uptrend'] and vsa_dom == 'BULLISH':
        overall_state = "CỔ PHIẾU ĐANG TĂNG MẠNH (Dòng tiền áp đảo, xu hướng chuẩn mực)."
    elif close < ma20 and close < ma50 and ichi['price_vs_kumo'] == 'below':
        overall_state = "CỔ PHIẾU ĐANG GIẢM MẠNH (Rơi tự do, mọi chỉ báo đều gãy)."
    elif accum['is_accumulation']:
        overall_state = "CỔ PHIẾU ĐANG TÍCH LŨY MẠNH NHƯ LÒ XO BỊ NÉN."
    elif close > ma20:
        overall_state = "CỔ PHIẾU ĐANG HƯỚNG LÊN TỪ TỪ (Uptrend sóng ngắn)."
    else:
        overall_state = "CỔ PHIẾU ĐANG GIAO DỊCH LÌNH XÌNH, KHÔNG CÓ XU HƯỚNG RÕ RÀNG."
        
    lines.append(f"  • Trạng thái chung: {overall_state}")
    
    # Khuyến nghị giao dịch
    entry = adv['entry_type']
    if entry != "NONE":
        lines.append(f"  • Khuyến nghị     : 🔥 ĐIỂM MUA  [{entry.replace('_', ' ')}] 🔥")
        lines.append(f"    - Mức độ tự tin : {adv['confidence']}")
        lines.append(f"    - Tỷ trọng g/ngân: {adv['position_size']}")
    else:
        if close > ma20:
            lines.append("  • Khuyến nghị     : TIẾP TỤC NẮM GIỮ (Hold) / Không nên mua đuổi lúc này.")
        elif accum['is_accumulation']:
            lines.append("  • Khuyến nghị     : CHỜ MUA (Wait & See) / Sẵn sàng giải ngân thăm dò khi bật nền.")
        else:
            lines.append("  • Khuyến nghị     : QUAN SÁT / CÂN NHẮC CẮT LỖ nếu vi phạm ngưỡng hỗ trợ.")
            
    if adv['risk_flags']:
        lines.append(f"  • Cảnh báo rủi ro : {', '.join(adv['risk_flags'])}")
        
    lines.append(sep)
    lines.append("")
    
    return "\n".join(lines)
