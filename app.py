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
from tinvest.storage_manager import StorageManager
from tinvest.vietstock_client import VietstockClient
from tinvest.config_manager import ConfigManager
import tkinter.simpledialog as simpledialog
from tkinter import scrolledtext
from datetime import datetime, timedelta

# --- GLOBAL WORKER FOR MULTIPROCESSING ---
def analyze_ticker_worker(ticker_df_tuple):
    """
    Hàm worker chạy trên các tiến trình riêng biệt.
    Phải nằm ở cấp độ module (top-level) để pickle được trên Windows.
    Sử dụng enrich_dataframe() tập trung để tránh tính toán trùng lặp.
    """
    ticker, df_sub = ticker_df_tuple
    try:
        from tinvest.data_loader import enrich_dataframe
        from tinvest.ichimoku_engine import analyze_ichimoku
        from tinvest.vsa_engine import analyze_vsa
        from tinvest.advanced_entry import classify_entry
        from tinvest.accumulation_engine import analyze_accumulation
        from tinvest.ma_engine import analyze_ma_trend
        from tinvest.valuation_engine import evaluate_stock_valuation
        
        # 1. Enrich data 1 lần duy nhất (MA, ATR, Ichimoku, HA, VSA helpers)
        df_rich = enrich_dataframe(df_sub.copy())
        
        # 2. Call engines — tất cả đều đọc columns đã có sẵn, không tính lại
        ichi = analyze_ichimoku(df_rich)
        vsa = analyze_vsa(df_rich)
        adv = classify_entry(df_rich)
        accum = analyze_accumulation(df_rich)
        ma_trend = analyze_ma_trend(df_rich)
        val = evaluate_stock_valuation(ticker, df_rich, adv)
        
        # Lưu df_rich (đã enrich) thay vì df raw để tái sử dụng cho breadth, scanner
        return ticker, {
            "df": df_rich,
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
        
        # Initialize Storage and API
        self.config_mgr = ConfigManager()
        self.storage = StorageManager()
        self.vs_client = VietstockClient()
        
        self._build_ui()
        
        # NOTE: Auto-load on startup disabled as per request.
        # Use the "📂 Load Dữ liệu Cũ" button instead.

    def _build_ui(self):
        # --- Top Frame: File Selection ---
        frame_top = tk.Frame(self.root, pady=10, padx=10)
        frame_top.pack(fill=tk.X)
        
        tk.Label(frame_top, text="1. Dữ liệu hệ thống:", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=5)
        self.lbl_file = tk.Label(frame_top, text="Chưa có dữ liệu (0 mã)...", fg="gray", font=("Arial", 10))
        self.lbl_file.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        btn_open = tk.Button(frame_top, text="📥 Nạp Thêm CSV", command=self.open_file, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), padx=5)
        btn_open.pack(side=tk.RIGHT, padx=2)

        btn_load = tk.Button(frame_top, text="📂 Load Dữ liệu Cũ", command=self.load_from_cache, bg="#795548", fg="white", font=("Arial", 10, "bold"), padx=5)
        btn_load.pack(side=tk.RIGHT, padx=2)

        btn_vs = tk.Button(frame_top, text="🌐 Cập Nhật Vietstock", command=self.run_vietstock_update, bg="#2196F3", fg="white", font=("Arial", 10, "bold"), padx=5)
        btn_vs.pack(side=tk.RIGHT, padx=2)

        btn_settings = tk.Button(frame_top, text="⚙️", command=self.open_settings, bg="#607D8B", fg="white", font=("Arial", 10, "bold"), padx=5)
        btn_settings.pack(side=tk.RIGHT, padx=2)

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
            
            self.log_sync(f"[1/4] Đang nạp thô {len(files)} file CSV...")
            dfs = []
            for f in files:
                try:
                    dfs.append(pd.read_csv(f))
                except: pass
            
            if not dfs:
                self.log_sync("Lỗi: Không đọc được file nào hợp lệ.")
                return
                
            self.log_sync("[2/4] Đang chuẩn hóa & Lưu vào Storage (CSV-First)...")
            raw_full = pd.concat(dfs, ignore_index=True)
            df_norm = _normalize_columns(raw_full)
            
            affected_tickers = set()
            if "Ticker" in df_norm.columns:
                grouped = df_norm.groupby("Ticker")
                for ticker_val, group in grouped:
                    t = str(ticker_val).upper().strip()
                    is_idx = ("VNINDEX" in t) or ("HNX" in t) or ("HAINDEX" in t)
                    if not (len(t) == 3 and t.isalnum()) and not is_idx:
                        continue
                    
                    sub_df = group.drop(columns=["Ticker"]).copy()
                    try:
                        clean_sub = _clean_dataframe(sub_df, ticker=t)
                        # Sync with CSV priority
                        t_min = self.storage.sync_prices(t, clean_sub, source='CSV')
                        if t_min is not None:
                            affected_tickers.add(t)
                    except: pass
            
            if not affected_tickers:
                self.log_sync("Không có thay đổi dữ liệu nào được ghi nhận.")
                return

            self.log_sync(f"[3/4] Đã cập nhật {len(affected_tickers)} mã. Đang tính toán chỉ báo...")
            self._sync_and_recompute_affected(list(affected_tickers))
            
            self.log_sync(f"\n✅ HOÀN TẤT NẠP DỮ LIỆU CSV!")
            
        except Exception as e:
            self.log_sync(f"\n❌ LỖI XỬ LÝ CSV: {str(e)}")

    def open_settings(self):
        """Mở cửa sổ cấu hình nâng cao để dán Header/cURL/URL từ trình duyệt."""
        top = tk.Toplevel(self.root)
        top.title("Cấu hình Vietstock nâng cao (Session/Token)")
        top.geometry("700x580")
        top.resizable(False, False)
        
        # Header Help
        frame_help = tk.LabelFrame(top, text="💡 Hướng dẫn lấy Token (Dùng để vượt giới hạn 200 mã)", font=("Arial", 10, "bold"), padx=10, pady=10, fg="#2E7D32")
        frame_help.pack(fill=tk.X, padx=10, pady=5)
        
        steps = (
            "📌 B1: Mở [finance.vietstock.vn] -> Tab [Thống kê giá].\n"
            "📌 B2: Nhấn [F12] -> Chọn tab [Network] (Mạng).\n"
            "📌 B3: Lọc dữ liệu trên Web để hiện dòng 'KQGDThongKeGiaPaging'.\n"
            "📌 B4: Chuột phải vào dòng đó -> Copy -> 'Copy Request Headers' (hoặc 'Copy as cURL').\n"
            "   (Hệ thống hiện hỗ trợ bóc tách linh hoạt từ Headers, cURL hoặc URL).\n"
            "📌 B5: Dán nội dung vào ô dưới và bấm Lưu."
        )
        tk.Label(frame_help, text=steps, justify=tk.LEFT, font=("Arial", 9)).pack(side=tk.LEFT)
        
        txt_area = scrolledtext.ScrolledText(top, width=80, height=15, font=("Consolas", 9))
        txt_area.pack(padx=10, pady=5)
        
        # Pre-fill current status info
        curr_token = self.config_mgr.get("payload_token") or "N/A"
        cookies = self.config_mgr.get("cookies") or {}
        txt_area.insert(tk.END, f"--- Trạng thái hiện tại ---\n")
        txt_area.insert(tk.END, f"Token: {curr_token[:30]}...\n")
        txt_area.insert(tk.END, f"Cookies: {len(cookies)} keys\n")
        txt_area.insert(tk.END, f"\n--- Dán Header/cURL/URL mới vào đây ---\n")

        def save_and_close():
            raw_text = txt_area.get("1.0", tk.END).strip()
            if not raw_text:
                top.destroy()
                return
            
            # Clean up previous status text if user didn't clear it
            if "--- Dán Header/cURL/URL mới vào đây ---" in raw_text:
                raw_text = raw_text.split("--- Dán Header/cURL/URL mới vào đây ---")[-1].strip()

            success = self.config_mgr.parse_input(raw_text)
            if success:
                # Force client refresh
                self.vs_client.refresh_from_config()
                
                new_token = self.config_mgr.get("payload_token")
                new_cookies = self.config_mgr.get("cookies")
                
                msg = f"Đã nhận diện thành công!\n\n- Token: {new_token[:20]}...\n- Cookies: {len(new_cookies)} mục.\n\nHệ thống đã lưu và áp dụng ngay."
                messagebox.showinfo("Thành công", msg)
                self.log_sync("✅ Đã cập nhật xong Session Vietstock mới.")
                top.destroy()
            else:
                messagebox.showerror("Lỗi", "Không tìm thấy Cookie hoặc Token hợp lệ. Hãy kiểm tra lại định dạng dán.")

        btn_row = tk.Frame(top)
        btn_row.pack(pady=10)
        
        tk.Button(btn_row, text="💾 Lưu & Cập Nhật", command=save_and_close, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), padx=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_row, text="❌ Hủy", command=top.destroy, padx=15).pack(side=tk.LEFT, padx=5)

    def load_from_cache(self):
        """Trigger cache loading in background thread."""
        self.log_sync("\n--- ĐANG TẢI DỮ LIỆU TỪ BỘ NHỚ ĐỆM (CACHE)... ---", clear=True)
        threading.Thread(target=self._load_from_cache_bg, daemon=True).start()

    def _load_from_cache_bg(self):
        try:
            tickers = self.storage.get_all_tickers()
            if not tickers:
                self.log_sync("Chưa có dữ liệu trong cache. Vui lòng bấm 'Cập Nhật Vietstock' hoặc 'Nạp Thêm CSV'.")
                return

            self.data_dict = {}
            self.analysis_cache = {}
            
            total = len(tickers)
            cnt = 0
            
            for t in tickers:
                # Load price
                df = self.storage.load_ticker_data(t)
                if df is not None:
                    self.data_dict[t] = df
                    
                    # Load analysis
                    analysis = self.storage.load_latest_analysis(t)
                    if analysis:
                        analysis['df'] = df
                        self.analysis_cache[t] = analysis
                
                cnt += 1
                if cnt % 50 == 0 or cnt == total:
                    self.log_sync(f" ---> Tiến trình: Đã nạp {cnt}/{total} mã cổ phiếu...")

            self._update_breadth_from_cache()
            self.root.after(0, self.lbl_file.config, {"text": f"Dữ liệu CACHE: {len(self.analysis_cache)} mã", "fg": "blue"})
            self.log_sync(f"✅ Hoàn tất! Đã nạp thành công {len(self.analysis_cache)} mã từ bộ nhớ đệm.")
            
        except Exception as e:
            self.log_sync(f"⚠️ Lỗi khi nạp cache: {e}")

    def run_vietstock_update(self):
        """Trigger incremental update from Vietstock API."""
        self.log_sync("\n--- BẮT ĐẦU CẬP NHẬT DỮ LIỆU TỪ VIETSTOCK API... ---", clear=True)
        threading.Thread(target=self._vietstock_update_bg, daemon=True).start()

    def _vietstock_update_bg(self):
        try:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            # If weekend, use Friday for the probe
            probe_date = today_str
            if now.weekday() == 5: 
                probe_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            elif now.weekday() == 6: 
                probe_date = (now - timedelta(days=2)).strftime("%Y-%m-%d")

            # --- STEP 1: IMMEDIATE SESSION PROBE ---
            self.log_sync(f"[*] Đang kiểm tra trạng thái URL (phiên thử nghiệm {probe_date})...", clear=True)
            _, is_limited = self.vs_client.fetch_market_day(1, probe_date)
            
            if is_limited:
                self.log_sync("! CẢNH BÁO: URL bị hạn chế (Chặn 200 mã). Hệ thống sẽ tự động kích hoạt chế độ nạp chia nhỏ (Bypass).")
                self.root.after(0, lambda: messagebox.showwarning("Cảnh báo URL", "Dữ liệu Vietstock bị giới hạn (200 mã/sàn).\n\nHệ thống sẽ dùng chế độ nạp chia nhỏ để lấy đủ mã cổ phiếu, nhưng bạn nên cập nhật cURL mới trong Cài đặt (⚙) để đạt tốc độ tốt nhất."))
            else:
                self.log_sync("✅ URL hoạt động tốt. Bắt đầu kiểm tra tính toàn vẹn dữ liệu...")

            # --- STEP 2: INTEGRITY CHECK (LAST 3 DAYS) ---
            last_date = self.storage.get_last_date()
            missing_dates = self.vs_client.get_missing_dates(last_date)
            
            check_dates = []
            current = last_date
            while len(check_dates) < 3 and current is not None:
                if current.weekday() < 5:
                    check_dates.append(current.strftime("%Y-%m-%d"))
                current -= timedelta(days=1)
            
            if check_dates:
                ticker_counts = self.storage.get_ticker_counts_for_dates(check_dates)
                # Ngưỡng: Nếu tổng số mã < 1200, coi là ngày bị thiếu sàn và cần xóa nạp lại.
                bad_dates = [d for d, count in ticker_counts.items() if count > 0 and count < 1200]
                if bad_dates:
                    self.log_sync(f"[*] Phát hiện {len(bad_dates)} ngày bị thiếu dữ liệu (< 1200 mã): {', '.join(bad_dates)}.")
                    self.log_sync(f"[*] Tiến hành xóa dữ liệu cũ của các ngày này để nạp bù...")
                    self.storage.delete_specific_dates(bad_dates)
                    # Merge with missing_dates and deduplicate
                    missing_dates = sorted(list(set(missing_dates) | set(bad_dates)))
            # --- END: 3-DAY CLEANUP LOGIC ---

            if not missing_dates:
                self.log_sync("✅ Dữ liệu đã được cập nhật mới nhất (SSoT).")
                self.log_sync("Gợi ý: Hãy bấm '📂 Load Dữ liệu Cũ' để nạp kết quả phân tích.")
                return

            self.log_sync(f"Tìm thấy {len(missing_dates)} ngày cần đồng bộ: {', '.join(missing_dates)}")
            
            affected_tickers = set()
            
            # --- STEP 3: FULL UPDATE ---
            for d in missing_dates:
                day_total = []
                self.log_sync(f"[*] Đang tải dữ liệu ngày {d}...")
                
                # Fetch Markets (HOSE=1, HNX=2, UPCOM=3)
                for cat_id, cat_name in [(1, "HOSE"), (2, "HNX"), (3, "UPCOM")]:
                    try:
                        raw, is_limited = self.vs_client.fetch_market_day(cat_id, d)
                        if is_limited:
                            self.log_sync(f"   ! CẢNH BÁO: {cat_name} bị giới hạn (200 mã).")
                        if raw:
                            day_total.extend(raw)
                            self.log_sync(f"   + {cat_name}: {len(raw)} mã.")
                    except Exception as e:
                        self.log_sync(f"   ! Lỗi {cat_name}: {e}")
                
                if day_total:
                    df_day = self.vs_client.format_to_df(day_total)
                    total_p1 = len(day_total)
                    self.log_sync(f"   ---> Ngày {d}: Tổng cộng nạp {total_p1} mã cổ phiếu.")
                    
                    if total_p1 < 1200:
                        self.log_sync(f"   ! CẢNH BÁO: Ngày {d} bị thiếu dữ liệu ({total_p1} < 1200 mã). URL hết hạn.")
                        
                    # Group by Ticker and sync to storage
                    for ticker, group in df_day.groupby("Ticker"):
                        try:
                            # SSoT: CSV > API is already handled inside storage.sync_prices
                            t_min = self.storage.sync_prices(ticker, group, source='API')
                            if t_min is not None: 
                                affected_tickers.add(ticker)
                        except: pass
                
                # Fetch Indices (VNINDEX=1, HNX-INDEX=2)
                indices = [("VNINDEX", 1, -19), ("HNX-INDEX", 2, -18)]
                for ticker, tid, sid in indices:
                    try:
                        idx_raw = self.vs_client.fetch_index_day(ticker, tid, sid, d)
                        if idx_raw:
                            day_idx = self.vs_client.format_to_df(idx_raw)
                            t_min = self.storage.sync_prices(ticker, day_idx, source='API')
                            if t_min is not None: affected_tickers.add(ticker)
                    except: pass

            if not affected_tickers:
                self.log_sync("✅ Dữ liệu đã được cập nhật mới nhất (SSoT).")
                self.log_sync("Gợi ý: Hãy bấm '📂 Load Dữ liệu Cũ' để nạp dữ liệu vào hệ thống phân tích.")
                return

            self.log_sync(f"✅ Hoàn tất! Đã cập nhật và đồng bộ {len(affected_tickers)} mã cổ phiếu.")
            self.log_sync("Hệ thống đã lưu dữ liệu mới nhất. Hãy bấm '📂 Load Dữ liệu Cũ' để cập nhật kết quả phân tích!")
            self.log_sync("Đang tính toán lại chỉ báo cho các mã bị ảnh hưởng...")
            self._sync_and_recompute_affected(list(affected_tickers))

        except Exception as e:
            self.log_sync(f"❌ Lỗi Vietstock Update: {e}")

    def _sync_and_recompute_affected(self, tickers):
        """Standard processing logic + saving results to Storage."""
        try:
            # 1. Load full history for affected tickers
            items = []
            for t in tickers:
                df_full = self.storage.load_ticker_data(t)
                if df_full is not None:
                    self.data_dict[t] = df_full
                    items.append((t, df_full))
            
            total = len(items)
            if total == 0: return
            
            cmp = 0
            batch_size = 20
            batches = [items[i:i + batch_size] for i in range(0, total, batch_size)]
            
            num_workers = min(os.cpu_count() or 4, 8)
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(analyze_batch_worker, b) for b in batches]
                for future in as_completed(futures):
                    batch_results = future.result()
                    for ticker, res in batch_results:
                        if res:
                            self.analysis_cache[ticker] = res
                            # SAVE TO STORAGE
                            self.storage.save_indicators(ticker, res['df'])
                            self.storage.save_analysis(ticker, res)
                    
                    cmp += len(batch_results)
                    self.log_sync(f" ---> Tiến độ: {cmp}/{total} mã...")

            self._update_breadth_from_cache()
            self.root.after(0, self.lbl_file.config, {"text": f"Dữ liệu: {len(self.analysis_cache)} mã", "fg": "blue"})
            self.log_sync("✅ Cập nhật hoàn tất!")

        except Exception as e:
            self.log_sync(f"❌ Lỗi xử lý: {e}")

    def _update_breadth_from_cache(self):
        """Recalculate market breadth from analysis_cache."""
        breadth_dfs = []
        for ticker, analysis in self.analysis_cache.items():
            try:
                df_sub = analysis["df"]
                temp = pd.DataFrame()
                temp['Date'] = df_sub['Date']
                temp['Valid'] = 1
                temp['>MA10'] = (df_sub['Close'] > df_sub['MA10']).astype(int)
                temp['>MA20'] = (df_sub['Close'] > df_sub['MA20']).astype(int)
                temp['>MA50'] = (df_sub['Close'] > df_sub['MA50']).astype(int)
                breadth_dfs.append(temp)
            except: pass
            
        if breadth_dfs:
            all_breadth = pd.concat(breadth_dfs)
            grouped = all_breadth.groupby('Date').sum()
            valid_counts = grouped['Valid'].replace(0, 1)
            mb = pd.DataFrame()
            mb['%MA10'] = (grouped['>MA10'] / valid_counts) * 100
            mb['%MA20'] = (grouped['>MA20'] / valid_counts) * 100
            mb['%MA50'] = (grouped['>MA50'] / valid_counts) * 100
            self.market_breadth = mb.sort_index()




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
            messagebox.showwarning("Cảnh báo", "Hệ thống chưa nạp dữ liệu. Hãy bấm '📂 Load Dữ liệu Cũ' hoặc 'Nạp Thêm File CSV'!")
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
            from tinvest.ichimoku_engine import analyze_ichimoku
            from tinvest.vsa_engine import analyze_vsa
            from tinvest.ma_engine import analyze_ma_trend
            
            # 1. Breadth (tính trước để truyền vào regime engine)
            breadth_res = analyze_market_breadth(self.data_dict, "VNINDEX")
            breadth_ma20 = breadth_res.get("strong_stocks_ma20_pct", 50.0)
            breadth_ma50 = breadth_res.get("strong_stocks_pct", 50.0)
            
            # Hàm phụ trợ chẩn bệnh nhanh Index
            def analyze_full_index(idx_df: pd.DataFrame):
                if idx_df is None or idx_df.empty: return None
                from tinvest.data_loader import enrich_dataframe
                from tinvest.advanced_entry import classify_entry
                from tinvest.valuation_engine import evaluate_stock_valuation
                
                # Enrich 1 lần duy nhất thay vì tính từng chỉ báo riêng lẻ
                df_rich = enrich_dataframe(idx_df.copy())
                
                # Tính momentum trước để truyền vào regime engine
                mom = analyze_momentum_divergence(idx_df)
                
                # Tín hiệu mua Index
                signals = classify_entry(df_rich)
                
                # S/R: Nếu có tín hiệu mua → dùng cách tính S/R của cổ phiếu (signal-aware)
                #       Nếu không có tín hiệu → dùng cách tính pivot-based cho thị trường giảm
                has_signal = signals.get('entry_type', 'NONE') != 'NONE'
                if has_signal:
                    val = evaluate_stock_valuation("INDEX", df_rich, signals)
                    sr = {"s1": val.get("s1", 0), "s2": val.get("s2", 0),
                          "r1": val.get("r1", 0), "r2": val.get("r2", 0)}
                else:
                    sr = calculate_index_sr(df_rich)
                
                return {
                    "regime": analyze_market_index(idx_df,
                                                   breadth_pct_ma20=breadth_ma20,
                                                   breadth_pct_ma50=breadth_ma50,
                                                   momentum_data=mom),
                    "momentum": mom,
                    "ichi": analyze_ichimoku(df_rich),
                    "vsa": analyze_vsa(df_rich),
                    "ma": analyze_ma_trend(df_rich),
                    "sr": sr,
                    "sr_source": "SIGNAL" if has_signal else "PIVOT",
                    "signals": signals
                }


            # 2. VNINDEX & HNXINDEX Data
            vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), "VNINDEX")
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
            report.append(f" - Tỷ lệ mã > MA20 (Dòng tiền ngắn hạn): {breadth_res.get('strong_stocks_ma20_pct', 'N/A')}%")
            report.append(f" - Tỷ lệ mã > MA50 (Dòng tiền khoẻ): {breadth_res['strong_stocks_pct']}%")
            report.append(f" - Số lượng Leader (Vượt đỉnh Vol to): {breadth_res['breakout_leaders']} mã")
            
            # Bảng Label các trạng thái (map tên kỹ thuật sang tên hiển thị)
            regime_labels = {
                "UPTREND": "📈 UPTREND (Tăng giá xác nhận)",
                "UPTREND_UNDER_PRESSURE": "⚠️ UPTREND RỦI RO (Tiềm ẩn áp lực)",
                "SIDEWAY": "↔️ SIDEWAY (Đi ngang/Tích lũy)",
                "MARKET_WEAKENING": "📉 SUY YẾU (Thị trường yếu dần)",
                "DOWNTREND": "🔴 DOWNTREND (Gấu/Điều chỉnh sâu)",
                "RECOVERY": "🟡 HỒI PHỤC (Đang thăm dò đáy)",
                "STABLE_RECOVERY": "🟢 HỒI PHỤC ỔN ĐỊNH (Có FTD sau đáy)",
                "UNKNOWN": "❓ CHƯA XÁC ĐỊNH"
            }
            
            def format_index(name, res_dict):
                if not res_dict or res_dict['regime']['regime'] == "UNKNOWN":
                    return f"\n--- TỔNG QUAN {name}: Không tìm thấy dữ liệu."
                
                res = res_dict['regime']
                mom = res_dict['momentum']
                ichi = res_dict['ichi']
                vsa = res_dict['vsa']
                ma = res_dict['ma']
                sr = res_dict.get('sr', {'s1':0, 's2':0, 'r1':0, 'r2':0})
                sr_source = res_dict.get('sr_source', 'PIVOT')
                sr_label = "Dựa trên tín hiệu mua" if sr_source == "SIGNAL" else "Dựa trên đỉnh/đáy lịch sử (thị trường không có tín hiệu)"
                
                regime_label = regime_labels.get(res['regime'], res['regime'])
                
                txt = f"\n--- TỔNG QUAN {name} ({res['date']})"
                txt += f"\n * TRẠNG THÁI: {regime_label}"
                txt += f"\n * HÀNH ĐỘNG: {res['action']}"
                
                txt += f"\n * NGƯỠNG KHÁNG CỰ (R): {sr['r1'] if sr['r1'] > 0 else 'N/A'} | {sr['r2'] if sr['r2'] > 0 else 'N/A'}"
                txt += f"\n * NGƯỠNG HỖ TRỢ (S): {sr['s1'] if sr['s1'] > 0 else 'N/A'} | {sr['s2'] if sr['s2'] > 0 else 'N/A'}"
                txt += f"\n   (Phương pháp S/R: {sr_label})"

                
                # FTD & RA Info
                if res['ftd_active']:
                    ftd_q = res.get('ftd_quality', 'N/A')
                    txt += f"\n   - FTD: Đang Kích Hoạt ({ftd_q})"
                elif res['ra_day'] > 0:
                    txt += f"\n   - Nỗ lực hồi phục (RA): Ngày thứ {res['ra_day']}"
                else:
                    txt += f"\n   - FTD: Chưa kích hoạt | RA: Chưa bắt đầu"
                
                # Mức giảm từ đỉnh
                decline_pct = res.get('decline_from_peak_pct', 0)
                if decline_pct > 5:
                    txt += f"\n   - ⚠️ Giảm từ đỉnh: -{decline_pct}%"
                    
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
            report.append("CHIẾN LƯỢC HÀNH ĐỘNG THEO TRẠNG THÁI:")
            report.append("─"*60)
            report.append("- UPTREND: 100% tỷ trọng, có thể Margin vào các Leader.")
            report.append("- UPTREND RỦI RO: Không mua đuổi (FOMO), chốt lời từng phần.")
            report.append("- SIDEWAY: Swing trade tại hỗ trợ, tỷ trọng 20-30%.")
            report.append("- SUY YẾU: Tiền mặt tối thiểu 50%, chỉ mua khi có tín hiệu rõ.")
            report.append("- DOWNTREND: Đứng ngoài. Chờ Nỗ lực hồi phục + FTD.")
            report.append("- HỒI PHỤC: Thăm dò 10-20%, mua cổ phiếu khỏe hơn TT.")
            report.append("- HỒI PHỤC ỔN ĐỊNH: Tăng 50-75%, tập trung Leader + tích nền.")
            
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
