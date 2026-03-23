"""
AIC code = AI + cơm! Desktop App
Giao diện người dùng cho hệ thống phân tích AIC code = AI + cơm!
"""
import tkinter as tk
from tkinter import filedialog, messagebox
from tinvest.data_loader import _normalize_columns, _clean_dataframe
from tinvest.analyzer import analyze_stock, format_report
import os
import pandas as pd
import threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed

# --- GLOBAL WORKER FOR MULTIPROCESSING ---
def analyze_ticker_worker(ticker_df_tuple):
    """
    Hàm worker chạy trên các tiến trình riêng biệt.
    Phải nằm ở cấp độ module (top-level) để pickle được trên Windows.
    """
    ticker, df_sub = ticker_df_tuple
    try:
        from tinvest.ichimoku_engine import analyze_ichimoku, compute_ichimoku
        from tinvest.vsa_engine import analyze_vsa
        from tinvest.advanced_entry import classify_entry
        from tinvest.accumulation_engine import analyze_accumulation
        from tinvest.ma_engine import analyze_ma_trend
        from tinvest.valuation_engine import evaluate_stock_valuation
        
        # 1. Pre-calculate common indicators
        df_rich = compute_ichimoku(df_sub.copy())
        
        df_rich['MA10'] = df_rich['Close'].rolling(10).mean()
        df_rich['MA20'] = df_rich['Close'].rolling(20).mean()
        df_rich['MA50'] = df_rich['Close'].rolling(50).mean()
        df_rich['MA100'] = df_rich['Close'].rolling(100).mean()
        df_rich['MA200'] = df_rich['Close'].rolling(200).mean()
        
        # ATR14
        h_l = df_rich['High'] - df_rich['Low']
        h_pc = (df_rich['High'] - df_rich['Close'].shift(1)).abs()
        l_pc = (df_rich['Low'] - df_rich['Close'].shift(1)).abs()
        tr = pd.concat([h_l, h_pc, l_pc], axis=1).max(axis=1)
        df_rich['ATR14'] = tr.rolling(14).mean()
        
        # AvgVolume20
        df_rich['AvgVolume20'] = df_rich['Volume'].rolling(20).mean()
        
        # 2. Call engines
        ichi = analyze_ichimoku(df_rich)
        vsa = analyze_vsa(df_rich)
        adv = classify_entry(df_rich)
        accum = analyze_accumulation(df_rich)
        ma_trend = analyze_ma_trend(df_rich)
        val = evaluate_stock_valuation(ticker, df_rich, adv)
        
        return ticker, {
            "df": df_sub,
            "ichi": ichi,
            "vsa": vsa,
            "adv": adv,
            "accum": accum,
            "ma_trend": ma_trend,
            "val": val
        }
    except Exception:
        return ticker, None

def analyze_batch_worker(batch):
    """Xử lý một nhóm (batch) mã cổ phiếu trong một tiến trình duy nhất."""
    results = []
    for item in batch:
        results.append(analyze_ticker_worker(item))
    return results

class TinvestApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AIC code = AI + cơm! - Hệ thống Phân tích Chứng khoán")
        self.root.geometry("850x650")
        
        self.data_dict = {}
        self.analysis_cache = {} # Lưu kêt quả tính toán sẵn để tránh delay
        
        self._build_ui()

    def _build_ui(self):
        # --- Top Frame: File Selection ---
        frame_top = tk.Frame(self.root, pady=10, padx=10)
        frame_top.pack(fill=tk.X)
        
        tk.Label(frame_top, text="1. Dữ liệu hệ thống:", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=5)
        self.lbl_file = tk.Label(frame_top, text="Chưa có dữ liệu (0 mã)...", fg="gray", font=("Arial", 10))
        self.lbl_file.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        btn_open = tk.Button(frame_top, text="📥 Nạp Thêm File CSV", command=self.open_file, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), padx=10)
        btn_open.pack(side=tk.RIGHT, padx=5)

        # --- Middle Frame: Action Buttons ---
        frame_mid = tk.Frame(self.root, pady=15, padx=10)
        frame_mid.pack(fill=tk.X)
        
        # Option 1: Analyzer
        frame_analyze = tk.LabelFrame(frame_mid, text="Phương án 1: Phân Tích Tổng Hợp 1 Mã", font=("Arial", 10, "bold"), pady=10, padx=10)
        frame_analyze.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Label(frame_analyze, text="Nhập mã chứng khoán (VD: HPG, VNM):").pack(side=tk.LEFT, padx=5)
        self.entry_ticker = tk.Entry(frame_analyze, width=10, font=("Arial", 12))
        self.entry_ticker.pack(side=tk.LEFT, padx=5)
        btn_analyze = tk.Button(frame_analyze, text="📈 Tra Cứu", command=self.run_analyzer, bg="#FF9800", fg="white", font=("Arial", 10, "bold"))
        btn_analyze.pack(side=tk.LEFT, padx=5)

        # --- Advanced Frame: 4 specific buttons ---
        frame_adv = tk.LabelFrame(self.root, text="Phương án 2: Bảng Điều Khiển Lọc (Scanner & Market)", font=("Arial", 10, "bold"), pady=10, padx=10)
        frame_adv.pack(fill=tk.X, padx=10, pady=5)
        
        # Row 1: Market Context (Breadth & Market Analysis)
        frame_market = tk.Frame(frame_adv)
        frame_market.pack(fill=tk.X, pady=2)
        
        btn_breadth = tk.Button(frame_market, text="📊 Chart Breadth (Độ rộng)", command=self.show_market_breadth, bg="#607D8B", fg="white", font=("Arial", 10, "bold"))
        btn_breadth.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        btn_market = tk.Button(frame_market, text="🏛️ Phân Tích Tổng Quan VNINDEX", command=self.run_market_analysis, bg="#E91E63", fg="white", font=("Arial", 10, "bold"))
        btn_market.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # Row 2: Basic Signals
        frame_signals_1 = tk.Frame(frame_adv)
        frame_signals_1.pack(fill=tk.X, pady=2)
        
        btn_early = tk.Button(frame_signals_1, text="🟢 Mua Sớm (EARLY)", command=lambda: self.run_advanced_scanner("EARLY"), bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        btn_early.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        btn_add1 = tk.Button(frame_signals_1, text="🟡 Gia Tăng 1 (ADD 1)", command=lambda: self.run_advanced_scanner("ADD_1"), bg="#FFC107", fg="black", font=("Arial", 10, "bold"))
        btn_add1.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        btn_add2 = tk.Button(frame_signals_1, text="🟡 Gia Tăng 2 (ADD 2)", command=lambda: self.run_advanced_scanner("ADD_2"), bg="#FF9800", fg="white", font=("Arial", 10, "bold"))
        btn_add2.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        btn_strong = tk.Button(frame_signals_1, text="🔴 Mua Mạnh (STRONG)", command=lambda: self.run_advanced_scanner("STRONG"), bg="#F44336", fg="white", font=("Arial", 10, "bold"))
        btn_strong.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        # Row 3: Advanced Filters & Recommendations
        frame_signals_2 = tk.Frame(frame_adv)
        frame_signals_2.pack(fill=tk.X, pady=2)
        
        btn_accum = tk.Button(frame_signals_2, text="📦 Cổ phiếu Tích Lũy", command=lambda: self.run_advanced_scanner("ACCUMULATION"), bg="#9C27B0", fg="white", font=("Arial", 10, "bold"))
        btn_accum.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        btn_ma = tk.Button(frame_signals_2, text="📈 Perfect MA", command=lambda: self.run_advanced_scanner("PERFECT_MA"), bg="#00BCD4", fg="white", font=("Arial", 10, "bold"))
        btn_ma.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        btn_trade = tk.Button(frame_signals_2, text="✅ Cổ phiếu TRADE", command=lambda: self.run_advanced_scanner("TRADEABLE"), bg="#008B8B", fg="white", font=("Arial", 10, "bold"))
        btn_trade.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        btn_wait = tk.Button(frame_signals_2, text="⏳ Cổ phiếu WAIT", command=lambda: self.run_advanced_scanner("WAIT"), bg="#D2691E", fg="white", font=("Arial", 10, "bold"))
        btn_wait.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        # --- Bottom Frame: Output / Results ---
        frame_bottom = tk.LabelFrame(self.root, text="Kết Quả", font=("Arial", 10, "bold"), padx=10, pady=10)
        frame_bottom.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Scrollable Text area for reports
        self.text_output = tk.Text(frame_bottom, font=("Consolas", 11), wrap=tk.WORD, state=tk.DISABLED)
        scrollbar = tk.Scrollbar(frame_bottom, command=self.text_output.yview)
        self.text_output.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.log_sync("Trạng thái: Sẵn sàng.\nVui lòng bấm 'Nạp Thêm File CSV' để tải tệp. (Không giới hạn số lượng file, hệ thống sẽ gom nhóm tự động và PRE-COMPUTE để lọc với tộc độ 0ms).")

    def _log_internal(self, message: str, clear: bool = False):
        self.text_output.configure(state=tk.NORMAL)
        if clear:
            self.text_output.delete(1.0, tk.END)
        self.text_output.insert(tk.END, message + "\n")
        self.text_output.see(tk.END)
        self.text_output.configure(state=tk.DISABLED)

    def log_sync(self, message: str, clear: bool = False):
        self.root.after(0, self._log_internal, message, clear)

    def open_file(self):
        files = filedialog.askopenfilenames(
            title="Chọn các file dữ liệu CSV",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if not files:
            return
            
        self.log_sync(f"\n--- BẮT ĐẦU XỬ LÝ {len(files)} FILE... ---", clear=True)
        threading.Thread(target=self._process_files_bg, args=(files,), daemon=True).start()

    def _process_files_bg(self, files):
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            # --- parallel loading ---
            self.log_sync(f"[1/5] Đang nạp thô {len(files)} file lên RAM (Song song)...")
            dfs = [None] * len(files)
            
            def _load_one(idx, path):
                try:
                    return idx, pd.read_csv(path)
                except Exception:
                    return idx, None

            with ThreadPoolExecutor(max_workers=min(32, len(files))) as loader_exec:
                load_futures = [loader_exec.submit(_load_one, i, f) for i, f in enumerate(files)]
                for fut in as_completed(load_futures):
                    i, df_raw = fut.result()
                    if df_raw is not None:
                        dfs[i] = df_raw
            
            dfs = [d for d in dfs if d is not None]
            
            if not dfs:
                self.log_sync("Lỗi: Không đọc được file nào hợp lệ.")
                return
                
            self.log_sync("[2/4] Đang chuẩn hóa & Phân tách mã (Song song)...")
            
            def _process_one_df(raw_df):
                try:
                    df_n = _normalize_columns(raw_df)
                    results = []
                    if "Ticker" in df_n.columns:
                        grouped = df_n.groupby("Ticker")
                        for ticker_val, group in grouped:
                            t = str(ticker_val).upper().strip()
                            is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
                            if not (len(t) == 3 and t.isalpha()) and not is_idx:
                                continue
                            sub_df = group.drop(columns=["Ticker"]).copy()
                            try:
                                c = _clean_dataframe(sub_df, ticker=t)
                                results.append((t, c))
                            except: pass
                    else:
                        try:
                            c = _clean_dataframe(df_n, ticker="SINGLE")
                            results.append(("SINGLE", c))
                        except: pass
                    return results
                except: return []

            with ThreadPoolExecutor(max_workers=16) as proc_exec:
                proc_futures = [proc_exec.submit(_process_one_df, d) for d in dfs]
                for fut in as_completed(proc_futures):
                    chunk_res = fut.result()
                    for t, c in chunk_res:
                        if t in self.data_dict:
                            self.data_dict[t] = pd.concat([self.data_dict[t], c]).drop_duplicates(subset=["Date"]).sort_values("Date")
                        else:
                            self.data_dict[t] = c

            total_valid = len(self.data_dict)
            self.log_sync(f" ---> Hoàn tất nạp dữ liệu. Đã nhận diện {total_valid} mã hợp lệ (3 ký tự).")
            
            for k, v in self.data_dict.items():
                self.data_dict[k] = v.sort_values(by="Date").reset_index(drop=True)

            self.log_sync("[3/4] Bắt đầu tính toán các chỉ báo kỹ thuật liên thị trường...")
            
            from tinvest.ichimoku_engine import analyze_ichimoku, compute_ichimoku
            from tinvest.vsa_engine import analyze_vsa
            from tinvest.advanced_entry import classify_entry
            from tinvest.accumulation_engine import analyze_accumulation
            from tinvest.ma_engine import analyze_ma_trend
            from tinvest.valuation_engine import evaluate_stock_valuation
            from concurrent.futures import ThreadPoolExecutor, as_completed

            total_compute = len(self.data_dict)
            self.analysis_cache = {}
            
            self.log_sync(f"[5/5] CẤU TRÚC LẠI DỮ LIỆU... Đang chạy đa tiến trình ({total_compute} mã)...")
            
            cmp = 0
            items = list(self.data_dict.items())
            
            # Gom nhóm (Batching): mỗi batch khoảng 20 mã để tối ưu hóa overhead tiến trình
            batch_size = 20
            batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
            
            import os
            num_workers = min(os.cpu_count() or 4, 8) # Ưu tiên dùng đa nhân thực (giống analogy 8 người 8 dao)
            
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                # Giao các batch cho các tiến trình
                futures = [executor.submit(analyze_batch_worker, b) for b in batches]
                
                for future in as_completed(futures):
                    batch_results = future.result()
                    for ticker, res in batch_results:
                        if res:
                            self.analysis_cache[ticker] = res
                    
                        cmp += 1
                        # In tiến độ
                        if cmp % max(10, int(total_compute*0.05)) == 0 or cmp == total_compute:
                            self.log_sync(f" ---> Tiến độ lập chỉ mục: {cmp}/{total_compute} mã ({int(cmp/total_compute*100)}%)...")

            self.log_sync("[6/6] Đang cập nhật Market Breadth (Độ Rộng Thị Trường) từ KQ tính toán...")
            breadth_dfs = []
            
            # Tái sử dụng kết quả đã tính toán trong analysis_cache để nhanh hơn
            for ticker, analysis in self.analysis_cache.items():
                try:
                    # analysis["df"] already has indicators if we pre-calculated them or if they are in the sub-engines
                    df_sub = analysis["df"]
                    
                    # Ensure MAs exist for breadth. 
                    # Note: _analyze_single adds MA10, MA20, MA50 to the df it returns if we store it
                    # But the 'df' in analysis might be the raw one. Let's make sure.
                    # Looking at _analyze_single, it calculates them on df_rich.
                    
                    # We need a DataFrame with Date, >MA10, >MA20, >MA50
                    temp = pd.DataFrame()
                    temp['Date'] = df_sub['Date']
                    
                    ma10 = df_sub['Close'].rolling(10).mean()
                    ma20 = df_sub['Close'].rolling(20).mean()
                    ma50 = df_sub['Close'].rolling(50).mean()
                    
                    temp['Valid'] = 1
                    temp['>MA10'] = (df_sub['Close'] > ma10).astype(int)
                    temp['>MA20'] = (df_sub['Close'] > ma20).astype(int)
                    temp['>MA50'] = (df_sub['Close'] > ma50).astype(int)
                    
                    breadth_dfs.append(temp)
                except Exception:
                    pass
                    
            if breadth_dfs:
                all_breadth = pd.concat(breadth_dfs)
                grouped = all_breadth.groupby('Date').sum()
                
                # Tránh chia cho 0
                valid_counts = grouped['Valid'].replace(0, 1)
                
                mb = pd.DataFrame()
                mb['%MA10'] = (grouped['>MA10'] / valid_counts) * 100
                mb['%MA20'] = (grouped['>MA20'] / valid_counts) * 100
                mb['%MA50'] = (grouped['>MA50'] / valid_counts) * 100
                
                self.market_breadth = mb.sort_index()
            else:
                self.market_breadth = pd.DataFrame()

            self.root.after(0, self.lbl_file.config, {"text": f"Đã nạp & tính toán {len(self.analysis_cache)} mã", "fg": "blue"})
            self.log_sync(f"\n✅ HOÀN TẤT NẠP DỮ LIỆU!\nHệ thống hiện giữ lịch sử & KQ phân tích sẵn sàng của {len(self.analysis_cache)} mã chứng khoán.\nBây giờ bạn bấm LỌC sẽ ra kết quả ngay lập tức!")
            
        except Exception as e:
            self.log_sync(f"\n❌ GẶP LỖI TRONG QUÁ TRÌNH GHÉP FILE: {str(e)}")




    def run_analyzer(self):
        if not self.data_dict:   
            messagebox.showwarning("Cảnh báo", "Vui lòng nạp dữ liệu!")
            return
            
        ticker = self.entry_ticker.get().strip().upper()
        if not ticker: return
            
        df = self.data_dict.get(ticker)
        if df is None:
            messagebox.showwarning("Không tìm thấy", f"Mã '{ticker}' không tồn tại hoặc dữ liệu <25 ngày!")
            return
            
        self.log_sync(f"Đang phân tích các tín hiệu của hãng {ticker} (cập nhật mới nhất)...", clear=True)
        self.root.update()
        
        try:
            from tinvest.analyzer import analyze_stock, format_report
            result = analyze_stock(ticker, df)
            report = format_report(result)
            self.log_sync(report, clear=True)
        except Exception as e:
            self.log_sync(f"Lỗi phân tích: {str(e)}")
            
    def run_advanced_scanner(self, entry_target: str):
        if not self.analysis_cache:
            messagebox.showwarning("Cảnh báo", "Hệ thống chưa nạp dữ liệu. Hãy bấm 'Nạp Thêm File CSV'!")
            return
            
        self.log_sync(f"Đang hiển thị các mã ứng với [{entry_target}] (thời gian tính 0ms)...", clear=True)
        self.root.update()
        
        try:
            results = []
            for ticker, data in self.analysis_cache.items():
                res = data["adv"]
                accum = data["accum"]
                val = data.get("val", {})
                
                df = data["df"]
                avg_vol_20 = df["Volume"].tail(20).mean() if len(df) >= 20 else df["Volume"].mean()

                match = False
                if entry_target == "ACCUMULATION":
                    if accum["is_accumulation"]:
                        match = True
                        size = "N/A"
                        conf = accum["base_quality"]
                        flags = "Ready to break" if accum["ready_to_break"] else ", ".join(accum["notes"])
                elif entry_target == "PERFECT_MA":
                    ma_trend = data.get("ma_trend", {})
                    if ma_trend.get("is_perfect_uptrend"):
                        match = True
                        size = "N/A"
                        conf = "HIGH"
                        flags = "MA10 > MA20 > MA50 > 100 > 200 (Giá > MA20 & Hỗ trợ MA50)"
                elif entry_target == "TRADEABLE":
                    action_str = val.get("action", "")
                    if action_str.startswith("YES"):
                        match = True
                        size = res.get("position_size", "N/A")
                        conf = res.get("confidence", "N/A")
                        flags = action_str
                elif entry_target == "WAIT":
                    action_str = val.get("action", "")
                    if action_str.startswith("WAIT"):
                        match = True
                        size = res.get("position_size", "N/A")
                        conf = res.get("confidence", "N/A")
                        flags = action_str
                else:
                    if res["entry_type"] == entry_target:
                        match = True
                        size = res["position_size"]
                        conf = res["confidence"]
                        flags = ", ".join(res["risk_flags"]) if res["risk_flags"] else "None"
                        
                if match:
                    # Skip if risk is too high (>15%) or invalid data
                    # (Nâng từ 10% lên 15% để phù hợp với các mã biến động mạnh - Penny/Midcap)
                    if not val.get("is_valid") or val.get("risk_pct", 0) > 15.0:
                        continue 
                        
                    # Time Logic
                    if entry_target in ["ACCUMULATION", "PERFECT_MA"]:
                        time_lbl = "T0"
                    else:
                        time_lbl = "T-1" if any("T-1" in flag for flag in res.get("risk_flags", [])) else "T0"
                        
                    # Reason Logic
                    if entry_target == "ACCUMULATION":
                        reason = f"Tích Lũy ({accum.get('base_quality', '')})"
                    elif entry_target == "PERFECT_MA":
                        reason = "Full MA Up"
                    else:
                        reason = res.get("details", {}).get("source", "System")
                        if reason == "MA": reason = "Moving Average"
                        elif reason == "ICHIMOKU": reason = "Ichimoku Cloud"
                        elif reason == "VSA": reason = "VSA Volume"
                    
                    last_vol = float(df['Volume'].iloc[-1])
                    # ep = risk.get("entry_price", 0)
                    # sl = risk.get("sl_price", 0)
                    # tp = risk.get("tp_price", 0)
                    # rr_ratio = round((tp - ep) / (ep - sl + 0.0001), 1) if ep > sl else 0
                    
                    ep = val.get("price", 0)
                    tp = val.get("tp1", 0)
                    rr_ratio = val.get("rr_ratio", 0)
                    
                    val_score = data.get("val", {}).get("risk_score", 0) if data.get("val") else 0
                    
                    # --- Results Table Columns ---
                    # Nhân 1000 cho Price, Entry, Target để về đơn vị VNĐ chuẩn
                    current_p = float(df['Close'].iloc[-1]) * 1000
                    results.append({
                        "Ticker": ticker,
                        "Price": f"{current_p:,.0f}",
                        "Volume": f"{last_vol:,.0f}",
                        "Entry": f"{ep*1000:,.0f}" if ep > 0 else "N/A",
                        "Target": f"{tp*1000:,.0f}" if tp > 0 else "N/A",
                        "RR": f"{round(rr_ratio, 1)}/1" if rr_ratio > 0 else "N/A",
                        "Risk Score": f"{int(val_score)}",
                        "Time": time_lbl,
                        "Reason": reason
                    })
                    
            if not results:
                self.log_sync(f"Hoàn tất: Không có mã nào đạt tiêu chí [{entry_target}].")
            else:
                self.log_sync(f"Hoàn tất: Tìm thấy {len(results)} mã thỏa mãn.\n")
                df_res = pd.DataFrame(results).sort_values("Ticker")
                table_str = df_res.to_string(index=False, justify="left")
                self.log_sync(table_str)
                self.log_sync("\n" + "="*70)
                self.log_sync("Thông tin: Hệ thống đã quét với toàn bộ thanh khoản thị trường.")
        except Exception as e:
            self.log_sync(f"Lỗi: {str(e)}")

    def run_market_analysis(self):
        if not self.data_dict:
            from tkinter import messagebox
            messagebox.showwarning("Cảnh báo", "Vui lòng nạp dữ liệu!")
            return
            
        self.log_sync("Đang xử lý Dữ liệu Thị trường (FTD, Phân phối, Breadth)...", clear=True)
        self.root.update()
        
        try:
            from tinvest.market_engine import analyze_market_index, analyze_market_breadth, evaluate_market_score, analyze_momentum_divergence, calculate_index_sr
            from tinvest.ichimoku_engine import compute_ichimoku, analyze_ichimoku
            from tinvest.vsa_engine import analyze_vsa
            from tinvest.ma_engine import analyze_ma_trend
            
            # 1. Breadth
            breadth_res = analyze_market_breadth(self.data_dict, "VNINDEX")
            
            # Hàm phụ trợ chẩn bệnh nhanh Index
            def analyze_full_index(idx_df: pd.DataFrame):
                if idx_df is None or idx_df.empty: return None
                df_rich = compute_ichimoku(idx_df.copy())
                # Thêm MAs
                df_rich['MA10'] = df_rich['Close'].rolling(10).mean()
                df_rich['MA20'] = df_rich['Close'].rolling(20).mean()
                df_rich['MA50'] = df_rich['Close'].rolling(50).mean()
                df_rich['MA100'] = df_rich['Close'].rolling(100).mean()
                df_rich['MA200'] = df_rich['Close'].rolling(200).mean()
                
                from tinvest.advanced_entry import classify_entry
                
                return {
                    "regime": analyze_market_index(idx_df),
                    "momentum": analyze_momentum_divergence(idx_df),
                    "ichi": analyze_ichimoku(df_rich),
                    "vsa": analyze_vsa(df_rich),
                    "ma": analyze_ma_trend(df_rich),
                    "sr": calculate_index_sr(idx_df),
                    "signals": classify_entry(idx_df)
                }

            # 2. VNINDEX & HNXINDEX Data
            vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), "VNINDEX")
            # If VNINDEX not found, maybe it's named VNI? But user said avoid VNI for index. 
            # Usually index data has VNINDEX as ticker.
            hn_key = next((k for k in self.data_dict.keys() if "HNX" in k or "HAINDEX" in k), "HNXINDEX")
            
            vn_full = analyze_full_index(self.data_dict.get(vn_key))
            hn_full = analyze_full_index(self.data_dict.get(hn_key))
            
            vn_res = vn_full['regime'] if vn_full else None
            hn_res = hn_full['regime'] if hn_full else None
            
            # 4. Master Score (VNINDEX is primary)
            if vn_res and vn_res['regime'] != "UNKNOWN":
                score_res = evaluate_market_score(vn_res, breadth_res)
                # Bơm thêm động lượng vào hệ điểm 
                if vn_full and vn_full['momentum']['rsi_divergence']: score_res['market_score'] = max(0, score_res['market_score'] - 2)
            elif hn_res and hn_res['regime'] != "UNKNOWN":
                score_res = evaluate_market_score(hn_res, breadth_res)
            else:
                score_res = {"market_score": 0, "health": "CHƯA RÕ"}
                
            report = []
            report.append("="*60)
            report.append("     BÁO CÁO TOÀN CẢNH THỊ TRƯỜNG CHUNG (MARKET REGIME)")
            report.append("="*60)
            
            report.append(f"\n1. ĐÁNH GIÁ SỨC KHOẺ: {score_res['market_score']}/10 ({score_res['health']})")
            
            report.append(f"\n2. ĐỘ RỘNG THỊ TRƯỜNG (BREADTH): {breadth_res['breadth_label']}")
            report.append(f" - Tổng mã quét: {breadth_res['total_scanned']}")
            report.append(f" - Số mã Tăng / Giảm: {breadth_res['advances']} / {breadth_res['declines']} (Đứng giá: {breadth_res['unaltered']})")
            report.append(f" - Tỷ lệ mã > MA50 (Dòng tiền khoẻ): {breadth_res['strong_stocks_pct']}%")
            report.append(f" - Số lượng Leader (Vượt đỉnh Vol to): {breadth_res['breakout_leaders']} mã")
            
            def format_index(name, res_dict):
                if not res_dict or res_dict['regime']['regime'] == "UNKNOWN":
                    return f"\n--- TỔNG QUAN {name}: Không tìm thấy dữ liệu."
                
                res = res_dict['regime']
                mom = res_dict['momentum']
                ichi = res_dict['ichi']
                vsa = res_dict['vsa']
                ma = res_dict['ma']
                sr = res_dict.get('sr', {'s1':0, 's2':0, 'r1':0, 'r2':0})
                
                txt = f"\n--- TỔNG QUAN {name} ({res['date']})"
                txt += f"\n * XU HƯỚNG CẤU TRÚC: {res['regime']}"
                txt += f"\n * HÀNH ĐỘNG: {res['action']}"
                
                txt += f"\n * NGƯỠNG KHÁNG CỰ (R): {sr['r1'] if sr['r1'] > 0 else 'N/A'} | {sr['r2'] if sr['r2'] > 0 else 'N/A'}"
                txt += f"\n * NGƯỠNG HỖ TRỢ (S): {sr['s1'] if sr['s1'] > 0 else 'N/A'} | {sr['s2'] if sr['s2'] > 0 else 'N/A'}"
                
                if res['regime'] == 'CONFIRMED UPTREND':
                    txt += f"\n   - FTD: Đang Kích Hoạt (An Toàn)"
                else:
                    txt += f"\n   - Nỗ lực hồi phục (RA): Ngày thứ {res['ra_day']}"
                    
                txt += f"\n   - Ngày Phân Phối (Supply): {res['distribution_count']} ngày"
                if res['distribution_count'] > 0:
                    txt += f" ({', '.join(res['distribution_dates'])})"
                
                # Bổ sung Indicators
                txt += f"\n * LƯỚI KỸ THUẬT (INDICATORS):"
                # VSA
                dominant_flow = "Dòng tiền VÀO" if vsa['dominant'] == 'bullish' else ("Dòng tiền CHỐT LỜI/RÚT RA" if vsa['dominant'] == 'bearish' else "Đi ngang Mất thanh khoản")
                txt += f"\n   - Giá/Khối lượng (VSA): {dominant_flow}"
                # Ichimoku
                txt += f"\n   - Đám mây (Ichimoku): Trend {ichi['trend']} (Màu {ichi['cloud_color']}) chạy {ichi['price_vs_kumo']} Kumo."
                # MA
                txt += f"\n   - Xu hướng MA: {ma['trend_label']} (Tăng nóng: {'CÓ' if ma['is_extended_up'] else 'KHÔNG'})"
                # Momentum
                rsi_alert = '- CHÚ Ý: Đang Phân Kỳ Âm (Báo Đỉnh)' if mom['rsi_divergence'] else ('- Vùng Xấu/Rủi ro' if mom['is_bad_zone'] else 'An Toàn')
                txt += f"\n   - Tâm lý (RSI 14): {mom['rsi_val']} {rsi_alert}"
                macd_alert = '- CHÚ Ý: MACD Phân Kỳ Đảo Chiều' if mom['macd_divergence'] else ''
                txt += f"\n   - Lực mua (MACD): {mom['macd_val']} (Hist: {mom['hist_val']}) {macd_alert}"

                # Bổ sung Tín hiệu Mua
                sigs = res_dict.get('signals', {})
                if sigs and sigs.get('entry_type') != "NONE":
                    etype = sigs['entry_type']
                    conf = sigs['confidence']
                    src = sigs.get('details', {}).get('source', '')
                    txt += f"\n 🔥 TÍN HIỆU: {etype} ({conf}) | Dựa trên: {src}"
                    if sigs.get('risk_flags'):
                        txt += f"\n   - Ghi chú: {', '.join(sigs['risk_flags'])}"
                
                return txt
                
            report.append(format_index(vn_key, vn_full).replace("---", "3."))
            if hn_full:
                report.append(format_index(hn_key, hn_full).replace("---", "4."))
                
            report.append("\n" + "="*60)
            report.append("CHÚ THÍCH HÀNH ĐỘNG:")
            report.append("- KHÔNG TRADE: Đứng ngoài tuyệt đối, Index gãy Trend / Chưa có FTD.")
            report.append("- TRADE NHỎ: Dành cho Sideway, chỉ tham gia khi có dòng tiền/Lead.")
            report.append("- TRADE MẠNH: Xác nhận Uptrend (Có FTD) + Phân phối an toàn.")
            
            self.log_sync("\n".join(report))
            
        except Exception as e:
            self.log_sync(f"Lỗi phân tích thị trường: {str(e)}")

    def show_market_breadth(self):
        if getattr(self, 'market_breadth', None) is None or self.market_breadth.empty:
            from tkinter import messagebox
            messagebox.showwarning("Cảnh báo", "Dữ liệu độ rộng thị trường chưa sẵn sàng. Vui lòng nạp file CSV!")
            return
            
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError:
            self.root.update()
            import sys
            import subprocess
            from tkinter import messagebox
            messagebox.showinfo("Đang Tự Cài Đặt", "Hệ thống đang bảo trì tự động cài 'matplotlib' cho bạn. Sẽ mất khoảng 5-10 giây, vui lòng chờ và KHÔNG tắt App...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib"])
                import matplotlib.pyplot as plt
                import matplotlib.dates as mdates
                messagebox.showinfo("Hoàn tất", "Tự cài xong thư viện! Biểu đồ sẽ hiển thị ngay bây giờ.")
            except Exception as e:
                messagebox.showerror("Chịu thua", f"Không thể tự cài. Vui lòng tự mở Command Prompt ở máy tính và chạy lệnh: pip install matplotlib\nChi tiết lỗi: {e}")
                return
            
        try:
            # 1. Lấy 2 năm giao dịch (~504 phiên)
            days = 504
            df_plot = self.market_breadth.tail(days).copy()
            if df_plot.empty:
                return
                
            dates = pd.to_datetime(df_plot.index)
            
            # Làm mượt đường line (Smoothing 5 phiên)
            smooth_win = 5
            df_plot['%MA20_smooth'] = df_plot['%MA20'].rolling(window=smooth_win, min_periods=1).mean()
            df_plot['%MA50_smooth'] = df_plot['%MA50'].rolling(window=smooth_win, min_periods=1).mean()
            
            fig, ax1 = plt.subplots(figsize=(14, 8))
            
            # 2. Vẽ 2 đường Line đã làm mượt (MA20, MA50)
            line2, = ax1.plot(dates, df_plot['%MA20_smooth'], color='blue', linestyle='-', label='% Cổ phiếu > MA20', linewidth=1.5)
            line3, = ax1.plot(dates, df_plot['%MA50_smooth'], color='purple', linestyle='-', label='% Cổ phiếu > MA50', linewidth=1.5)
            
            ax1.set_title('Độ Rộng Thị Trường & CHỈ SỐ VNINDEX - 2 Năm Qua', fontsize=14, fontweight='bold')
            ax1.set_xlabel('Thời Gian', fontsize=11)
            ax1.set_ylabel('Tỉ Lệ Phần Trăm (%)', fontsize=11)
            ax1.grid(True, linestyle='--', alpha=0.6)
            
            # 3. Chèn text % hiện tại ở cuối mỗi đường line
            last_date = dates[-1]
            last_ma20 = df_plot['%MA20_smooth'].iloc[-1]
            last_ma50 = df_plot['%MA50_smooth'].iloc[-1]
            
            ax1.annotate(f'{last_ma20:.1f}%', xy=(last_date, last_ma20), xytext=(5, 0), textcoords='offset points', color='blue', fontweight='bold', va='center')
            ax1.annotate(f'{last_ma50:.1f}%', xy=(last_date, last_ma50), xytext=(5, 0), textcoords='offset points', color='purple', fontweight='bold', va='center')
            
            # 4. Chèn biểu đồ nến VNINDEX (Dựa trên dữ liệu data_dict)
            df_vnindex = self.data_dict.get("VNINDEX")
            
            if df_vnindex is not None and not df_vnindex.empty:
                # Trục bên phải
                ax2 = ax1.twinx()
                df_vn = df_vnindex.copy()
                df_vn['Date'] = pd.to_datetime(df_vn['Date'])
                df_vn = df_vn.sort_values("Date")
                
                # Cắt đúng khoảng thời gian của ax1
                df_vn = df_vn[(df_vn['Date'] >= dates.min()) & (df_vn['Date'] <= dates.max())]
                
                df_vn['DateNum'] = mdates.date2num(df_vn['Date'])
                
                up = df_vn[df_vn['Close'] >= df_vn['Open']]
                down = df_vn[df_vn['Close'] < df_vn['Open']]
                
                width = 0.8 # Độ rộng nến
                
                # Vẽ bóng nến (Wick)
                ax2.vlines(up['DateNum'], up['Low'], up['High'], color='green', linewidth=1, alpha=0.3)
                ax2.vlines(down['DateNum'], down['Low'], down['High'], color='red', linewidth=1, alpha=0.3)
                
                # Vẽ thân nến (Body)
                ax2.bar(up['DateNum'], up['Close'] - up['Open'], bottom=up['Open'], color='green', width=width, alpha=0.3, label='VNINDEX')
                ax2.bar(down['DateNum'], down['Open'] - down['Close'], bottom=down['Close'], color='red', width=width, alpha=0.3)
                
                ax2.set_ylabel('Điểm VNINDEX', fontsize=11, color='#555555')
                ax2.tick_params(axis='y', labelcolor='#555555')
                
                # Gộp Legend
                lines1, labels1 = ax1.get_legend_handles_labels()
                lines2, labels2 = ax2.get_legend_handles_labels()
                # Không hiển thị 2 lần label VNINDEX
                if lines2:
                    dict_leg = dict(zip(labels1 + ["VNINDEX (Nến mờ)"], lines1 + [lines2[0]]))
                    ax1.legend(dict_leg.values(), dict_leg.keys(), loc='upper left')
                else: ax1.legend(loc='upper left')
            else:
                ax1.legend(loc='upper left')
                print("Không tìm thấy VNINDEX trong Data để vẽ nến.")
            
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%Y'))
            try:
                ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            except: pass
            
            fig.autofmt_xdate()
            # Mở rộng nhẹ trục x để chừa không gian cho Text bên phải
            ax1.set_xlim(dates.min(), dates.max() + pd.Timedelta(days=20))
            
            plt.tight_layout()
            plt.show()
        except Exception as e:
            from tkinter import messagebox
            import traceback
            messagebox.showerror("Lỗi biểu đồ", f"Lỗi khi vẽ: {str(e)}\n{traceback.format_exc()}")

if __name__ == "__main__":
    root = tk.Tk()
    app = TinvestApp(root)
    root.mainloop()
