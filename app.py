"""
AIC code = AI + cơm! Desktop App
Giao diện người dùng cho hệ thống phân tích AIC code = AI + cơm!
"""
import tkinter as tk
from tkinter import filedialog, messagebox
from tinvest.data_loader import _normalize_columns, _clean_dataframe
from tinvest.scanner import _action_label
from tinvest.analyzer import analyze_stock, format_report
import os
import pandas as pd
import threading

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
        
        # Option 1: Scanner
        frame_scan = tk.LabelFrame(frame_mid, text="Phương án 1: Lọc Cổ Phiếu Tốt", font=("Arial", 10, "bold"), pady=10, padx=10)
        frame_scan.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Label(frame_scan, text="Lọc danh sách các mã đạt điểm 8 - 11").pack(pady=5)
        btn_scan = tk.Button(frame_scan, text="🔍 Lọc Cổ Phiếu (Score ≥ 8)", command=self.run_scanner, bg="#2196F3", fg="white", font=("Arial", 10, "bold"))
        btn_scan.pack(pady=5)

        # Option 2: Analyzer
        frame_analyze = tk.LabelFrame(frame_mid, text="Phương án 2: Phân Tích 1 Mã", font=("Arial", 10, "bold"), pady=10, padx=10)
        frame_analyze.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        
        tk.Label(frame_analyze, text="Nhập mã chứng khoán (VD: HPG, VNM):").pack(side=tk.LEFT, padx=5)
        self.entry_ticker = tk.Entry(frame_analyze, width=10, font=("Arial", 12))
        self.entry_ticker.pack(side=tk.LEFT, padx=5)
        btn_analyze = tk.Button(frame_analyze, text="📈 Tra Cứu", command=self.run_analyzer, bg="#FF9800", fg="white", font=("Arial", 10, "bold"))
        btn_analyze.pack(side=tk.LEFT, padx=5)

        # --- Advanced Frame: 4 specific buttons ---
        frame_adv = tk.LabelFrame(self.root, text="Phương án 3: Lọc Chuyên Sâu (Advanced Entry & Tích Lũy)", font=("Arial", 10, "bold"), pady=10, padx=10)
        frame_adv.pack(fill=tk.X, padx=10, pady=5)
        
        frame_adv_top = tk.Frame(frame_adv)
        frame_adv_top.pack(fill=tk.X)
        
        btn_early = tk.Button(frame_adv_top, text="🟢 Mua Sớm (EARLY)", command=lambda: self.run_advanced_scanner("EARLY"), bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        btn_early.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        btn_add1 = tk.Button(frame_adv_top, text="🟡 Gia Tăng 1 (ADD 1)", command=lambda: self.run_advanced_scanner("ADD_1"), bg="#FFC107", fg="black", font=("Arial", 10, "bold"))
        btn_add1.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        btn_add2 = tk.Button(frame_adv_top, text="🟡 Gia Tăng 2 (ADD 2)", command=lambda: self.run_advanced_scanner("ADD_2"), bg="#FF9800", fg="white", font=("Arial", 10, "bold"))
        btn_add2.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        btn_strong = tk.Button(frame_adv_top, text="🔴 Mua Mạnh (STRONG)", command=lambda: self.run_advanced_scanner("STRONG"), bg="#F44336", fg="white", font=("Arial", 10, "bold"))
        btn_strong.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        frame_adv_bot = tk.Frame(frame_adv)
        frame_adv_bot.pack(fill=tk.X, pady=5)
        
        btn_accum = tk.Button(frame_adv_bot, text="📦 Cổ phiếu Tích Lũy (Chờ Breakout)", command=lambda: self.run_advanced_scanner("ACCUMULATION"), bg="#9C27B0", fg="white", font=("Arial", 10, "bold"))
        btn_accum.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        btn_ma = tk.Button(frame_adv_bot, text="📈 Xu Hướng Hoàn Hảo (Perfect MA)", command=lambda: self.run_advanced_scanner("PERFECT_MA"), bg="#00BCD4", fg="white", font=("Arial", 10, "bold"))
        btn_ma.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        btn_breadth = tk.Button(frame_adv_bot, text="📊 Market Breadth (1 Năm)", command=self.show_market_breadth, bg="#607D8B", fg="white", font=("Arial", 10, "bold"))
        btn_breadth.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

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
            self.log_sync(f"[1/5] Đang nạp thô {len(files)} file lên RAM...")
            dfs = []
            for i, f in enumerate(files):
                try:
                    dfs.append(pd.read_csv(f))
                except Exception:
                    pass
                if (i + 1) % 50 == 0:
                    self.log_sync(f" ---> Đã đọc được {i + 1}/{len(files)} file.")
            
            if not dfs:
                self.log_sync("Lỗi: Không đọc được file nào hợp lệ.")
                return
                
            self.log_sync("[2/5] Ghép nối toàn bộ dữ liệu thành 1 chuỗi liên tục (Merging)...")
            raw = pd.concat(dfs, ignore_index=True)
            
            self.log_sync("[3/5] Cấu trúc chuẩn hóa & làm sạch cột...")
            df = _normalize_columns(raw)
            
            self.log_sync("[4/5] Phân rã dữ liệu theo từng mã chứng khoán (1-2 giây)!")
            if "Ticker" in df.columns:
                grouped = df.groupby("Ticker")
                total_tickers = len(grouped)
                
                valid_count = 0
                for ticker_val, group in grouped:
                    ticker = str(ticker_val).upper()
                    
                    if not (len(ticker) == 3 and ticker.isalpha()) and ticker not in ["VNINDEX", "HNXINDEX"]:
                        continue
                        
                    sub = group.drop(columns=["Ticker"]).copy()
                    
                    try:
                        cleaned = _clean_dataframe(sub, ticker=ticker)
                        if ticker in self.data_dict:
                            merged = pd.concat([self.data_dict[ticker], cleaned]).drop_duplicates(subset=["Date"]).sort_values("Date")
                            self.data_dict[ticker] = merged
                        else:
                            self.data_dict[ticker] = cleaned
                            
                        valid_count += 1
                    except Exception:
                        pass
                    
                    if valid_count % 100 == 0 and valid_count > 0:
                        self.log_sync(f" ---> Đã lưu chuỗi thời gian phân tích cho mã thứ {valid_count}...")
            else:
                self.log_sync("Phát hiện CSV chỉ có 1 mã không có cột Ticker, sẽ tự xếp là SINGLE...")
                self.data_dict["SINGLE"] = _clean_dataframe(df.copy(), ticker="SINGLE")

            for k, v in self.data_dict.items():
                self.data_dict[k] = v.sort_values(by="Date").reset_index(drop=True)

            self.log_sync("[5/5] CẤU TRÚC LẠI DỮ LIỆU... Tính toán bộ lọc Ichimoku, VSA, HA trước (Pre-computing)... Vài giây...")
            
            from tinvest.ichimoku_engine import analyze_ichimoku
            from tinvest.vsa_engine import analyze_vsa
            from tinvest.aic_engine import analyze_aic
            from tinvest.scoring_engine import calculate_score
            from tinvest.advanced_entry import classify_entry
            from tinvest.accumulation_engine import analyze_accumulation
            from tinvest.ma_engine import analyze_ma_trend
            from tinvest.risk_engine import calculate_stoploss
            from concurrent.futures import ThreadPoolExecutor

            total_compute = len(self.data_dict)
            self.analysis_cache = {}
            
            # --- 5.1 CHIA NHỎ CÔNG ĐOẠN: Tính toán đa luồng (Optimized) ---
            def _analyze_single(ticker_df_tuple):
                ticker, df_sub = ticker_df_tuple
                try:
                    # 1. Pre-calculate common indicators to share across engines
                    from tinvest.ichimoku_engine import compute_ichimoku
                    df_rich = compute_ichimoku(df_sub)
                    
                    df_rich['MA10'] = df_rich['Close'].rolling(10).mean()
                    df_rich['MA20'] = df_rich['Close'].rolling(20).mean()
                    df_rich['MA50'] = df_rich['Close'].rolling(50).mean()
                    df_rich['MA100'] = df_rich['Close'].rolling(100).mean()
                    df_rich['MA200'] = df_rich['Close'].rolling(200).mean()
                    
                    # 2. Call engines using the enriched DataFrame
                    ichi = analyze_ichimoku(df_rich)
                    vsa = analyze_vsa(df_rich)
                    aic = analyze_aic(df_rich)
                    score = calculate_score(ichi, vsa, aic)
                    adv = classify_entry(df_rich)
                    accum = analyze_accumulation(df_rich)
                    ma_trend = analyze_ma_trend(df_rich)
                    risk = calculate_stoploss(df_rich, adv["entry_type"], float(df_sub["Close"].iloc[-1]), adv.get("details"))
                    
                    return ticker, {
                        "df": df_sub,
                        "ichi": ichi,
                        "vsa": vsa,
                        "aic": aic,
                        "score": score,
                        "adv": adv,
                        "accum": accum,
                        "ma_trend": ma_trend,
                        "risk": risk
                    }
                except Exception:
                    return ticker, None

            self.log_sync(f"[5/5] CẤU TRÚC LẠI DỮ LIỆU... Đang chạy song song {total_compute} mã (Tốc độ cao)...")
            
            cmp = 0
            # Sử dụng ThreadPoolExecutor để tận dụng CPU (Pandas/Numpy release GIL)
            # Max workers có thể để None (mặc định) hoặc giới hạn ví dụ 10-20
            with ThreadPoolExecutor(max_workers=None) as executor:
                results = executor.map(_analyze_single, self.data_dict.items())
                
                for ticker, res in results:
                    if res:
                        self.analysis_cache[ticker] = res
                    
                    cmp += 1
                    # Cập nhật log thường xuyên hơn (mỗi 20 mã hoặc 5%) để tránh cảm giác bị treo
                    if cmp % 20 == 0 or cmp == total_compute:
                        self.log_sync(f" ---> Tiến độ: {cmp}/{total_compute} mã ({int(cmp/total_compute*100)}%)...")

            self.log_sync("[6/6] Đang phân tích Market Breadth (Độ Rộng Thị Trường)...")
            breadth_dfs = []
            for ticker, df in self.data_dict.items():
                try:
                    temp = pd.DataFrame()
                    temp['Date'] = df['Date']
                    
                    ma10 = df['Close'].rolling(10).mean()
                    ma20 = df['Close'].rolling(20).mean()
                    ma50 = df['Close'].rolling(50).mean()
                    
                    temp['Valid'] = 1
                    temp['>MA10'] = (df['Close'] > ma10).astype(int)
                    temp['>MA20'] = (df['Close'] > ma20).astype(int)
                    temp['>MA50'] = (df['Close'] > ma50).astype(int)
                    
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


    def run_scanner(self):
        if not self.analysis_cache:
            messagebox.showwarning("Cảnh báo", "Hệ thống chưa lập chỉ mục hoặc nạp dữ liệu!")
            return
            
        self.log_sync("Đang lấy từ bộ nhớ các mã đạt 8 - 11 điểm (thời gian tính: 0ms)...", clear=True)
        self.root.update()
        
        try:
            results = []
            for ticker, data in self.analysis_cache.items():
                if data["score"]["total_score"] >= 8:
                    df = data["df"]
                    last_close = float(df["Close"].iloc[-1])
                    
                    results.append({
                        "Ticker": ticker,
                        "Price": round(last_close, 2),
                        "Trend": data["ichi"]["trend"],
                        "MoneyFlow": data["vsa"]["dominant"].capitalize(),
                        "Trigger": data["aic"]["setup"],
                        "Score": data["score"]["total_score"],
                        "Classification": data["score"]["classification"],
                        "Action": _action_label(data["score"]["classification"], data["aic"]["setup"])
                    })
                    
            if not results:
                self.log_sync("Hoàn tất: Không có mã nào đạt điểm >= 8.")
            else:
                self.log_sync(f"Hoàn tất: Tìm thấy {len(results)} mã đạt tiêu chuẩn tiềm năng (Score >= 8).\n")
                df_res = pd.DataFrame(results).sort_values("Score", ascending=False)
                table_str = df_res.to_string(index=False, justify="left")
                self.log_sync(table_str)
                self.log_sync("\n" + "="*70)
                self.log_sync("Gợi ý: Nhập mã chứng khoán tương ứng vào ô 'Tra Cứu' để phân tích chi tiết.")
        except Exception as e:
            messagebox.showerror("Lỗi khi lọc", str(e))
            self.log_sync(f"Lỗi: {str(e)}")

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
                        flags = "MA10 > MA20 > MA50 > 100 > 200 (MA10 Up)"
                else:
                    if res["entry_type"] == entry_target:
                        match = True
                        size = res["position_size"]
                        conf = res["confidence"]
                        flags = ", ".join(res["risk_flags"]) if res["risk_flags"] else "None"
                        
                if match:
                    risk = data.get("risk", {})
                    if not risk.get("is_valid", True):
                        continue # Skip high risk signals (>10%)
                        
                    results.append({
                        "Ticker": ticker,
                        "Entry": risk.get("entry_price", 0),
                        "SL": risk.get("sl_price", 0),
                        "Target": risk.get("tp_price", 0),
                        "Risk%": f"{risk.get('risk_pct', 0)}%",
                        "Confidence/Quality": conf,
                        "Notes/Risks": flags
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

    def show_market_breadth(self):
        if getattr(self, 'market_breadth', None) is None or self.market_breadth.empty:
            messagebox.showwarning("Cảnh báo", "Dữ liệu độ rộng thị trường chưa sẵn sàng. Vui lòng nạp file CSV!")
            return
            
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
