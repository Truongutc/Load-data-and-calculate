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


from tinvest.data_loader import enrich_dataframe


from tinvest.ichimoku_engine import analyze_ichimoku


from tinvest.vsa_engine import analyze_vsa


from tinvest.advanced_entry import classify_entry


from tinvest.accumulation_engine import analyze_accumulation


from tinvest.ma_engine import analyze_ma_trend


from tinvest.valuation_engine import evaluate_stock_valuation





# --- GLOBAL WORKER FOR MULTIPROCESSING ---


def analyze_ticker_worker(ticker_df_tuple):


    """


    Hàm worker hỗ trợ ThreadPoolExecutor.


    Các import phải nằm ngoài để tránh Deadlock do Import Lock của Python.


    """


    ticker, df_sub = ticker_df_tuple


    try:


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


        # --- Top Frame: Dashboard Controls ---


        frame_top = tk.Frame(self.root, pady=8, padx=10)


        frame_top.pack(fill=tk.X)


        


        tk.Label(frame_top, text="Dữ liệu:", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=2)


        self.lbl_file = tk.Label(frame_top, text="Chưa có (0)", fg="gray", font=("Arial", 10))


        self.lbl_file.pack(side=tk.LEFT, padx=5)


        


        # Right container for actions


        frame_btns = tk.Frame(frame_top)


        frame_btns.pack(side=tk.RIGHT)





        btn_settings = tk.Button(frame_btns, text="⚙️", command=self.open_settings, bg="#607D8B", fg="white", font=("Arial", 9, "bold"), width=3)


        btn_settings.pack(side=tk.RIGHT, padx=2)





        btn_open = tk.Button(frame_btns, text="📥 Nạp CSV", command=self.open_file, bg="#4CAF50", fg="white", font=("Arial", 9, "bold"), padx=8)


        btn_open.pack(side=tk.RIGHT, padx=2)





        btn_load = tk.Button(frame_btns, text="📂 Load Cache", command=self.load_from_cache, bg="#795548", fg="white", font=("Arial", 9, "bold"), padx=8)


        btn_load.pack(side=tk.RIGHT, padx=2)





        btn_vs = tk.Button(frame_btns, text="🌐 Update", command=self.run_vietstock_update, bg="#2196F3", fg="white", font=("Arial", 9, "bold"), padx=8)


        btn_vs.pack(side=tk.RIGHT, padx=2)





        self.lbl_session = tk.Label(frame_top, text="🌐 URL: Checking...", font=("Arial", 9, "bold"), fg="#666")


        self.lbl_session.pack(side=tk.RIGHT, padx=10)


        


        # Initial status check


        self.root.after(1000, self.update_session_ui)





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





        btn_chart = tk.Button(frame_analyze, text="📊 Biểu Đồ", command=self.run_stock_chart, bg="#2196F3", fg="white", font=("Arial", 10, "bold"))


        btn_chart.pack(side=tk.LEFT, padx=5)





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

        btn_white_adx = tk.Button(frame_signals_2, text="⚪ Trend MẠNH (ADX)", command=lambda: self.run_advanced_scanner("WHITE_ADX"), bg="#FFFFFF", fg="black", font=("Arial", 10, "bold"))
        btn_white_adx.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)





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





            self.log_sync(f"[3/4] Đã cập nhật {len(affected_tickers)} mã. Đang tính toán chỉ bá✅..")


            self._sync_and_recompute_affected(list(affected_tickers))


            


            self.log_sync(f"\n✅ HOÀN TẤT NẠP DỮ LIỆU CSV!")


            


        except Exception as e:


            self.log_sync(f"\n❌ LỖI XỬ LÝ CSV: {str(e)}")





    def update_session_ui(self):


        """Update the green/red session status indicator."""


        def run_check():


            status = self.vs_client.check_session_status()


            def apply_ui():


                if status in ["VALID", "LIMITED_BYPASSED"]:


                    self.lbl_session.config(text="🌐 URL: Đang Hoạt Động (Full)", fg="#2E7D32")


                elif status == "LIMITED":


                    self.lbl_session.config(text="🌐 URL: Lỗi (Chỉ lấy được 200 mã)", fg="#D32F2F")


                elif status == "NO_DATA":


                    self.lbl_session.config(text="🌐 URL: Không có dữ liệu hôm nay", fg="#F57C00")


                else:


                    self.lbl_session.config(text="🌐 URL: Lỗi kết nối", fg="#F57C00")


            self.root.after(0, apply_ui)


        threading.Thread(target=run_check, daemon=True).start()





    def open_settings(self):


        """Mở cửa sổ cấu hình nâng cao để dán cURL hoặc Headers từ trình duyệt."""


        top = tk.Toplevel(self.root)


        top.title("Cấu hình Vietstock (Vượt giới hạn 200 mã)")


        top.geometry("750x680")


        top.resizable(False, False)


        


        # Header Help


        frame_help = tk.LabelFrame(top, text="💡 Cách lấy dữ liệu 1 chạm (Khuyên dùng)", font=("Arial", 10, "bold"), padx=10, pady=10, fg="#2E7D32")


        frame_help.pack(fill=tk.X, padx=10, pady=5)


        


        steps = (


            "📌 B1: Truy cập [finance.vietstock.vn] -> Tab [Thống kê giá].\n"


            "📌 B2: Nhấn [F12] -> Chọn tab [Network] (Mạng).\n"


            "📌 B3: Chuột phải vào 'KQGDThongKeGiaPaging' -> Copy -> 'Copy as cURL (bash)'.\n"


            "📌 B4: Quay lại đây, nhấn [📋 Dán từ Clipboard] -> [💾 Lưu & Cập Nhật].\n"


            "--------------------------------------------------------------------------\n"


            "🚀 Mẹo: Bạn chỉ cần Copy toàn bộ mã cURL, phần mềm sẽ tự bóc tách mọi thứ."


        )


        tk.Label(frame_help, text=steps, justify=tk.LEFT, font=("Arial", 9)).pack(side=tk.LEFT)





        # Bookmarklet Section


        frame_bm = tk.Frame(top, padx=10)


        frame_bm.pack(fill=tk.X)


        


        def copy_bookmarklet():


            bm_code = "javascript:(function(){alert('Hướng dẫn: F12 -> Network -> Chuột phải KQGDThongKeGiaPaging -> Copy as cURL (bash)');})()"


            self.root.clipboard_clear()


            self.root.clipboard_append(bm_code)


            messagebox.showinfo("Bookmarklet", "Đã copy mã Bookmarklet vào Clipboard!\n\nHãy tạo 1 Bookmark mới trên trình duyệt và dán mã này vào phần URL.")





        tk.Button(frame_bm, text="🔗 Copy mã hỗ trợ (Bookmarklet)", command=copy_bookmarklet, bg="#607D8B", fg="white", font=("Arial", 8)).pack(side=tk.RIGHT)


        


        txt_area = scrolledtext.ScrolledText(top, width=85, height=18, font=("Consolas", 9))


        txt_area.pack(padx=10, pady=5)


        


        # Pre-fill current status info


        curr_token = self.config_mgr.get("payload_token") or "N/A"


        cookies = self.config_mgr.get("cookies") or {}


        txt_area.insert(tk.END, f"--- DÁN MÃ cURL HOẶC HEADERS VÀO ĐÂY ---\n")


        txt_area.insert(tk.END, f"(Trạng thái hiện tại: Token {curr_token[:15]}..., Cookies: {len(cookies)} keys)\n\n")





        def paste_from_clipboard():


            try:


                clipboard = self.root.clipboard_get()


                txt_area.delete("1.0", tk.END)


                txt_area.insert(tk.END, clipboard)


            except:


                messagebox.showerror("Lỗi", "Không thể đọc dữ liệu từ Clipboard.")





        def save_and_close():


            raw_text = txt_area.get("1.0", tk.END).strip()


            if not raw_text or "DÁN MÃ cURL" in raw_text:


                top.destroy()


                return


            


            success = self.config_mgr.parse_input(raw_text)


            if success:


                self.vs_client.refresh_from_config()


                top.destroy() # Close window immediately


                


                # Check status and show warning ONLY if truly blocked


                def run_bg_check():


                    status = self.vs_client.check_session_status()


                    def apply_ui():


                        if status in ["VALID", "LIMITED_BYPASSED"]:


                             self.lbl_session.config(text="🌐 URL: Đang Hoạt Động (Full Mã)", fg="#2E7D32")


                             self.log_sync("✅ URL hoàn toàn hợp lệ, sẵn sàng tải 100% dữ liệu.")


                        elif status == "LIMITED":


                             self.lbl_session.config(text="🌐 URL: Lỗi (Bị Cắt 200 mã)", fg="#D32F2F")


                             self.log_sync("❌ CẢNH BÁO: URL Bị Chặn. Chỉ lấy được tối đa 200 mã!")


                             messagebox.showerror("Bị Chặn 200 Mã", "❌ URL hoặc Cookie này đã bị vô hiệu hóa kỹ thuật Bypass.\nDữ liệu tải về sẽ bị thiếu hụt!\n\nVui lòng làm theo hướng dẫn:\n1. Sang tab [Network] chọn lại kích thước hiển thị 50 mã/trang.\n2. Bấm lật trang 2 và Copy lại mã cURL mới nhất.")


                        elif status == "NO_DATA":


                             self.lbl_session.config(text="🌐 URL: Không có dữ liệu", fg="#F57C00")


                             self.log_sync("✅ URL kích hoạt thành công (Hôm nay không có dữ liệu giao dịch).")


                        else:


                             self.lbl_session.config(text="🌐 URL: Mất kết nối", fg="#F57C00")


                             messagebox.showerror("Lỗi Mạng", "Không thể kết nối đến máy chủ Vietstock.")


                             


                    self.root.after(0, apply_ui)


                


                self.log_sync("Đang xác thực bảo mật URL...")


                self.lbl_session.config(text="🌐 URL: Đang xác thực...", fg="#2196F3")


                threading.Thread(target=run_bg_check, daemon=True).start()


            else:


                messagebox.showerror("Lỗi", "Không tìm thấy thông tin hợp lệ trong nội dung bạn dán.")





        btn_row = tk.Frame(top)


        btn_row.pack(pady=10)


        


        tk.Button(btn_row, text="📋 Dán từ Clipboard", command=paste_from_clipboard, bg="#2196F3", fg="white", font=("Arial", 10, "bold"), padx=15).pack(side=tk.LEFT, padx=5)


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


            # --- STEP 1: INITIAL CHECK ---


            self.log_sync(f"[*] Bắt đầu kiểm tra tính toàn vẹn dữ liệu (SSoT)...", clear=True)


            self.update_session_ui() # Refresh visual indicator





            # --- STEP 2: INTEGRITY CHECK (LAST 3 TRADING DAYS) ---


            # If any day has < 1000 tickers (heuristic for 200-limit error), we treat it as missing.


            last_date = self.storage.get_last_date()


            missing_dates = self.vs_client.get_missing_dates(last_date)


            


            check_dates = []


            current = last_date or datetime.now()


            while len(check_dates) < 3 and current is not None:


                if current.weekday() < 5:


                    check_dates.append(current.strftime("%Y-%m-%d"))


                current -= timedelta(days=1)


            


            if check_dates:


                self.log_sync(f"[*] Đang quét 3 ngày gần nhất để tìm dữ liệu lỗi: {', '.join(check_dates)}...")


                ticker_counts = self.storage.get_ticker_counts_for_dates(check_dates)


                


                # Threshold < 1000 because total stocks HOSE+HNX+UPCOM should be ~1600+


                # If it's < 1000, it means at least one exchange was truncated at 200.


                bad_dates = [d for d, count in ticker_counts.items() if count > 0 and count < 1000]


                if bad_dates:


                    self.log_sync(f"⚠️ Phát hiện {len(bad_dates)} ngày bị thiếu mã (< 1000 mã): {', '.join(bad_dates)}")


                    self.log_sync(f"[*] Đang xóa và chuẩn bị nạp lại dữ liệu đầy đủ cho các ngày lỗi...")


                    self.storage.delete_specific_dates(bad_dates)


                    # Merge with missing_dates and deduplicate


                    missing_dates = sorted(list(set(missing_dates) | set(bad_dates)))





            # --- FORCE UPDATE CURRENT TRADING DAY ---


            now = datetime.now()


            effective_today = now.date()


            if now.weekday() == 5: effective_today -= timedelta(days=1)


            elif now.weekday() == 6: effective_today -= timedelta(days=2)


            eff_today_str = effective_today.strftime("%Y-%m-%d")


            


            if eff_today_str not in missing_dates:


                missing_dates.append(eff_today_str)


                missing_dates = sorted(missing_dates)





            if not missing_dates:


                self.log_sync("✅ Dữ liệu đã đầy đủ và mới nhất (SSoT).")


                self.log_sync("Gợi ý: Hãy bấm '📂 Load Dữ liệu Cũ' để hiển thị kết quả phân tích.")


                return





            self.log_sync(f"Tìm thấy {len(missing_dates)} ngày cần đồng bộ: {', '.join(missing_dates)}")


            


            affected_tickers = set()


            


            # --- STEP 3: FULL UPDATE ---


            for i, d in enumerate(missing_dates):


                day_total = []


                self.log_sync(f"\n--- [Ngày {i+1}/{len(missing_dates)}] ĐANG TẢI: {d} ---")


                


                # Fetch Markets (HOSE=1, HNX=2, UPCOM=3)


                for cat_id, cat_name in [(1, "HOSE"), (2, "HNX"), (3, "UPCOM")]:


                    try:


                        self.log_sync(f"   + Đang nạp {cat_name}...")


                        raw, is_limited = self.vs_client.fetch_market_day(cat_id, d)


                        # Suppressed is_limited bypass log per user request


                        if raw:


                            day_total.extend(raw)


                            self.log_sync(f"   ---> Xong {cat_name}: {len(raw)} mã.")


                    except Exception as e:


                        self.log_sync(f"   ! Lỗi {cat_name}: {e}")


                


                if day_total:


                    df_day = self.vs_client.format_to_df(day_total)


                    total_p1 = len(day_total)


                    self.log_sync(f"   [DONE] Ngày {d}: Tổng cộng {total_p1} mã.")


                    


                    if total_p1 < 1000:


                        self.log_sync(f"   ! LƯU Ý: Dữ liệu ngày {d} vẫn bị thiếu (Gói Limited).")


                        


                    # Group by Ticker and sync to storage


                    tickers_in_day = df_day["Ticker"].unique()


                    for idx, (ticker, group) in enumerate(df_day.groupby("Ticker")):


                        try:


                            t_min = self.storage.sync_prices(ticker, group, source='API')


                            if t_min is not None: 


                                affected_tickers.add(ticker)


                            


                            # Log progress every 100 tickers to keep it visual


                            if idx > 0 and idx % 200 == 0:


                                self.log_sync(f"      ... Đang lưu dữ liệu: {idx}/{len(tickers_in_day)} mã...")


                        except: pass


                


                # Fetch Indices (VNINDEX=1, HNX-INDEX=2)


                self.log_sync(f"   + Đang nạp Indices (VNINDEX, HNX-INDEX)...")


                indices = [("VNINDEX", 1, -19), ("HNX-INDEX", 2, -18)]


                for ticker, tid, sid in indices:


                    try:


                        idx_raw = self.vs_client.fetch_index_day(ticker, tid, sid, d)


                        if idx_raw:


                            day_idx = self.vs_client.format_to_df(idx_raw)


                            self.storage.sync_prices(ticker, day_idx, source='API')


                            # Always force update UX/Indicators for Indices if fetch succeeds


                            affected_tickers.add(ticker)


                            self.log_sync(f"   ---> Xong Index: {ticker} ({d})")


                    except Exception as e:


                        self.log_sync(f"   ! Lỗi Index {ticker}: {e}")





            if not affected_tickers:


                self.log_sync("\n✅ Dữ liệu đã được cập nhật mới nhất (SSoT).")


                self.log_sync("Gợi ý: Hãy bấm '📂 Load Dữ liệu Cũ' để nạp kết quả phân tích.")


                return





            self.log_sync(f"\n✅ HOÀN TẤT NẠP DỮ LIỆU! Đã đồng bộ {len(affected_tickers)} mã.")


            self.log_sync("--- ĐANG TÍNH TOÁN LẠI CHỈ BÁO VÀ SCANNER (0ms) ---")


            


            # Use progress updates in _sync_and_recompute_affected


            self._sync_and_recompute_affected(list(affected_tickers))


            


            self.log_sync(f"\n✨ TẤT CẢ ĐÃ SẴN SÀNG! Đã cập nhật xong {len(affected_tickers)} mã.")


            self.log_sync("Gợi ý: Hãy bấm '📂 Load Dữ liệu Cũ' để hiển thị bảng xếp hạng mới nhất.")





        except Exception as e:


            self.log_sync(f"\n❌ LỖI VIETSTOCK UPDATE: {e}")





    def _sync_and_recompute_affected(self, tickers):


        """


        Optimized incremental processing logic.


        Uses existing memory cache if available to avoid heavy Disk I/O and serialization.


        """


        try:


            items_to_recompute = []


            


            # --- STEP 1: LOAD OR PATCH DATA ---


            for t in tickers:


                # If already in memory, we skip full disk reload and use memory DF


                if t in self.data_dict and self.data_dict[t] is not None:


                    # Sync happened on storage, so we should actually reload to be 100% sure


                    # BUT for speed, I'll only reload if we are not sure.


                    # Actually, the storage sync just appended to the file.


                    # For now, let's reload because it's safer, but use cache to store it.


                    df_full = self.storage.load_ticker_data(t)


                    if df_full is not None:


                        self.data_dict[t] = df_full


                        items_to_recompute.append((t, df_full))


                else:


                    # FRESH LOAD


                    df_full = self.storage.load_ticker_data(t)


                    if df_full is not None:


                        self.data_dict[t] = df_full


                        items_to_recompute.append((t, df_full))


            


            total = len(items_to_recompute)


            if total == 0: return


            


            self.log_sync(f" ---> Đang tính toán chỉ báo cho {total} mã...")


            


            cmp = 0


            # INCREASE batch_size to reduce process startup and pickling overhead


            batch_size = 50 


            batches = [items_to_recompute[i:i + batch_size] for i in range(0, total, batch_size)]


            


            # Switched to ThreadPoolExecutor: Because passing 1600+ big DataFrames 


            # across Process boundaries (Pickling) is extremely slow and caused the bottleneck.


            # Pandas and Numpy release the GIL for core calculations anyway.


            num_workers = min((os.cpu_count() or 4) * 2, 16) 


            with ThreadPoolExecutor(max_workers=num_workers) as executor:


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


                    if cmp % 200 == 0 or cmp == total:


                         self.log_sync(f"      ... Tiến độ: {cmp}/{total} mã...")





            self._update_breadth_from_cache()


            self.root.after(0, self.lbl_file.config, {"text": f"Dữ liệu: {len(self.analysis_cache)} mã", "fg": "blue"})


            self.log_sync("✅ Cập nhật hoàn tất!")





        except Exception as e:


            self.log_sync(f"❌ Lỗi xử lý: {e}")





    def _update_breadth_from_cache(self):


        """Recalculate market breadth from analysis_cache."""


        if len(self.analysis_cache) < 100:


            return  # Prevent breadth corruption when only a few tickers were updated incrementally


            


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
                elif entry_target == "WHITE_ADX":
                    from tinvest.advanced_entry import _get_adx_status
                    if _get_adx_status(df, -1) == "WHITE":
                        match = True
                        size = "N/A"
                        conf = "STRONG"
                        flags = "ADX Trắng (Rising & DI+ > DI-)"
                        val["risk_pct"] = val.get("risk_pct", 0) * 0.7  # Relax risk for scanner display


                else:


                    if res["entry_type"] == entry_target:


                        match = True


                        size = res["position_size"]


                        conf = res["confidence"]


                        flags = ", ".join(res["risk_flags"]) if res["risk_flags"] else "None"


                        


                if match:


                    # Skip if risk is too high or invalid data
                    risk_limit = 20.0 if entry_target == "WHITE_ADX" else 15.0
                    if not val.get("is_valid") or val.get("risk_pct", 0) > risk_limit:
                        continue 


                        


                    time_lbl = "T0" if entry_target in ["ACCUMULATION", "PERFECT_MA"] else ("T-1" if any("T-1" in flag for flag in res.get("risk_flags", [])) else "T0")


                    if entry_target == "ACCUMULATION":
                        reason = f"Tích Lũy ({accum.get('base_quality', '')})"
                    elif entry_target == "PERFECT_MA":
                        reason = "Full MA Up"
                    elif entry_target == "WHITE_ADX":
                        reason = "ADX TRẮNG"
                    else:
                        reason = res.get("details", {}).get("source", "System")


                    


                    ep = val.get("price", 0)


                    tp = val.get("tp1", 0)


                    rr_ratio = val.get("rr_ratio", 0)


                    val_score = data.get("val", {}).get("risk_score", 0) if data.get("val") else 0


                    current_p = float(df['Close'].iloc[-1]) * 1000
                    last_vol = float(df["Volume"].iloc[-1])


                    


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





    def run_stock_chart(self):


        """Displays a professional technical analysis chart for the selected stock."""


        ticker = self.entry_ticker.get().upper().strip()


        if not ticker:


            messagebox.showwarning("Cảnh báo", "Vui lòng nhập mã chứng khoán!")


            return


            


        df = self.data_dict.get(ticker)


        if df is None or df.empty:


            messagebox.showwarning("Lỗi", f"Không tìm thấy dữ liệu cho mã [{ticker}]. Hãy nạp dữ liệu trước!")


            return


            


        self.log_sync(f"\n--- ĐANG KHỞI TẠO BIỂU ĐỒ: {ticker} ---")


        


        def chart_task():


            try:


                import matplotlib.pyplot as plt


                import matplotlib.dates as mdates


                import numpy as np


                from tinvest.data_loader import enrich_dataframe


                


                # Enrich data to ensure all indicators (MA, Ichimoku, VSA) are present


                df_rich = enrich_dataframe(df.copy())


                


                # Take last 150 days for visibility


                df_plot = df_rich.tail(150).copy()


                df_plot['Date'] = pd.to_datetime(df_plot['Date'])


                df_plot = df_plot.sort_values('Date')


                # --- NEW: Extend for Ichimoku Future (26 periods) ---


                last_date = df_plot['Date'].iloc[-1]


                future_dates = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=26)


                df_future = pd.DataFrame({'Date': future_dates})


                df_ext = pd.concat([df_plot, df_future], ignore_index=True)


                


                # --- Fix Ichimoku Cloud Plotting (Future Alignment) ---


                df_rich['raw_a'] = (df_rich['Tenkan'] + df_rich['Kijun']) / 2


                df_rich['raw_b'] = (df_rich['High'].rolling(52).max() + df_rich['Low'].rolling(52).min()) / 2


                


                hist_cloud = df_rich[['Date', 'SpanA', 'SpanB']].tail(150).copy()


                


                future_spans = []


                for i in range(1, 27):


                    source_idx = -26 + i


                    val_a = df_rich['raw_a'].iloc[source_idx] if abs(source_idx) <= len(df_rich) else np.nan


                    val_b = df_rich['raw_b'].iloc[source_idx] if abs(source_idx) <= len(df_rich) else np.nan


                    future_spans.append({'Date': df_future['Date'].iloc[i-1], 'SpanA': val_a, 'SpanB': val_b})


                


                df_future_cloud = pd.DataFrame(future_spans)


                df_total_cloud = pd.concat([hist_cloud, df_future_cloud], ignore_index=True)





                # Subsets for Candlesticks


                up = df_plot[df_plot['Close'] >= df_plot['Open']]


                down = df_plot[df_plot['Close'] < df_plot['Open']]





                # Fetch analysis...


                analysis = self.analysis_cache.get(ticker, {})


                val = analysis.get('val', {})


                adv = analysis.get('adv', {})


                


                # Create fig (Thinner height for standard screen)


                fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10), gridspec_kw={'height_ratios': [4, 1.2]}, sharex=True)


                plt.subplots_adjust(hspace=0.03, bottom=0.15)


                


                # Plot Candlesticks...


                ax1.bar(mdates.date2num(up['Date']), up['Close'] - up['Open'], bottom=up['Open'], color='green', width=0.6, alpha=0.8)


                ax1.bar(mdates.date2num(down['Date']), down['Open'] - down['Close'], bottom=down['Close'], color='red', width=0.6, alpha=0.8)


                ax1.vlines(mdates.date2num(up['Date']), up['Low'], up['High'], color='green', linewidth=1)


                ax1.vlines(mdates.date2num(down['Date']), down['Low'], down['High'], color='red', linewidth=1)


                


                # Plot MAs...


                ma_styles = [('MA10', 'black', 'MA10', 2), ('MA20', 'green', 'MA20', 2), ('MA50', 'brown', 'MA50', 1)]


                for ma_col, color, label, lw in ma_styles:


                    if ma_col in df_plot.columns:


                        ax1.plot(df_plot['Date'], df_plot[ma_col], label=label, color=color, linewidth=lw, alpha=0.8)


                


                # Plot Ichimoku Cloud


                ax1.fill_between(df_total_cloud['Date'], df_total_cloud['SpanA'], df_total_cloud['SpanB'], 


                                 where=(df_total_cloud['SpanA'] >= df_total_cloud['SpanB']), color='lime', alpha=0.3, label='Kumo Green')


                ax1.fill_between(df_total_cloud['Date'], df_total_cloud['SpanA'], df_total_cloud['SpanB'], 


                                 where=(df_total_cloud['SpanA'] < df_total_cloud['SpanB']), color='red', alpha=0.3, label='Kumo Red')


                    


                if 'Tenkan' in df_plot.columns:


                    ax1.plot(df_plot['Date'], df_plot['Tenkan'], color='blue', label='Tenkan', linewidth=1.0, alpha=0.9)


                if 'Kijun' in df_plot.columns:


                    ax1.plot(df_plot['Date'], df_plot['Kijun'], color='red', label='Kijun', linewidth=1.0, alpha=0.9)


                if 'Kijun65' in df_plot.columns:


                    ax1.plot(df_plot['Date'], df_plot['Kijun65'], color='orange', linestyle='--', label='Dao 65', linewidth=2.0, alpha=0.8)





                # Scaling: Limit Y axis to price area


                p_min, p_max = df_plot['Low'].min(), df_plot['High'].max()


                ax1.set_ylim(p_min * 0.95, p_max * 1.05)


                


                # Plot S1, S2, R1, R2 lines...


                if val:


                    sr_config = [('s1', 'green', 'S1'), ('s2', 'darkgreen', 'S2'), 


                                 ('r1', 'red', 'R1'), ('r2', 'darkred', 'R2')]


                    for sr_key, color, lbl in sr_config:


                        level = val.get(sr_key, 0)


                        if level > 0:


                            ax1.axhline(level, color=color, linestyle='--', alpha=0.8, linewidth=1.5)


                            ax1.text(df_ext['Date'].iloc[0], level, f" {lbl}: {level:,.0f}", color=color, 


                                     fontsize=9, fontweight='bold', va='bottom', alpha=1.0)


                


                # Signals... (up to 3 arrows)


                from tinvest.advanced_entry import _eval_day


                buy_signals = []


                for idx in df_plot.index.tolist():


                    rel_idx = -(len(df_rich) - df_rich.index.get_loc(idx))


                    sig = _eval_day(df_rich, rel_idx)


                    if sig and sig.get('type') in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:


                        buy_signals.append({'date': df_rich['Date'].loc[idx], 'type': sig['type'], 


                                           'source': sig.get('details', {}).get('source', 'N/A'), 'price': df_rich['Low'].loc[idx]})


                


                buy_signals = sorted(buy_signals, key=lambda x: x['date'], reverse=True)[:3]


                annotation_text = "3 ĐIỂM MUA GẦN NHẤT:\n"


                for i, b in enumerate(buy_signals):


                    ax1.plot(b['date'], b['price'] * 0.98, '^', markersize=12, color='lime', markeredgecolor='green')


                    annotation_text += f" • #{i+1}: {b['date'].strftime('%d/%m')} - {b['type']} ({b['source']})\n"


                


                if buy_signals:


                    fig.text(0.1, 0.02, annotation_text, fontsize=10, color='darkgreen', 


                             bbox=dict(facecolor='white', alpha=0.8, edgecolor='lime'))





                # Volume...


                ax2.bar(mdates.date2num(df_plot['Date']), df_plot['Volume'], 


                        color=np.where(df_plot['Close'] >= df_plot['Open'], 'green', 'red'), alpha=0.5, width=0.6)


                if 'VolMA20' in df_plot.columns:


                    ax2.plot(df_plot['Date'], df_plot['VolMA20'], color='blue', alpha=0.6)





                # Final Layout


                ax1.set_title(f"TECHNICAL ANALYSIS CHART: {ticker}", fontsize=14, fontweight='bold', color='darkblue')


                ax1.grid(True, linestyle='--', alpha=0.3)


                ax1.legend(loc='upper left', fontsize=9, ncol=4)


                ax1.set_xlim(mdates.date2num(df_ext['Date'].iloc[0]), mdates.date2num(df_ext['Date'].iloc[-1]))


                ax2.grid(True, linestyle='--', alpha=0.3)


                ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))


                plt.show()


                


            except Exception as e:


                import traceback


                self.log_sync(f"❌ LỖI VẼ BIỂU ĐỒ [{ticker}]: {e}")


                print(traceback.format_exc())


                


        import threading


        threading.Thread(target=chart_task, daemon=True).start()





    def run_market_analysis(self):


        if not self.data_dict:


            from tkinter import messagebox


            messagebox.showwarning("Cảnh báo", "Vui lòng nạp dữ liệu!")


            return


            


        self.log_sync("Đang xử lý Dữ liệu Thị trường (FTD, Phân phối, Breadth)...", clear=True)


        


        def analyze_task():


            try:


                from tinvest.market_engine import analyze_market_index, analyze_market_breadth, analyze_momentum_divergence, calculate_index_sr


                from tinvest.ichimoku_engine import analyze_ichimoku


                from tinvest.vsa_engine import analyze_vsa


                from tinvest.ma_engine import analyze_ma_trend


                


                breadth_res = analyze_market_breadth(self.data_dict, "VNINDEX")


                breadth_ma20 = breadth_res.get("strong_stocks_ma20_pct", 50.0)


                breadth_ma50 = breadth_res.get("strong_stocks_pct", 50.0)


                


                regime_labels = {


                    "UPTREND": "📈 UPTREND (Tăng giá xác nhận)",


                    "UPTREND_UNDER_PRESSURE": "⚠️ UPTREND RỦI RO (Suy yếu/Phân phối)",


                    "STABLE_RECOVERY": "🔵 HỒI PHỤC ỔN ĐỊNH (Trên MA20/Kijun)",


                    "RECOVERY": "🟡 HỒI PHỤC (FTD và trên MA10)",


                    "WEAK_RECOVERY": "⚪ HỒI PHỤC YẾU (Có RA Day 3+)",


                    "SIDEWAY": "↔️ SIDEWAY (Đi ngang quanh MA50)",


                    "MARKET_WEAKENING": "📉 SUY YẾU (Giá dưới MA50)",


                    "DOWNTREND": "🔴 DOWNTREND (Thị trường giảm giá)",


                    "UNKNOWN": "❓ CHƯA XÁC ĐỊNH"


                }





                def analyze_full_index(idx_df: pd.DataFrame):


                    if idx_df is None or idx_df.empty: return None


                    from tinvest.data_loader import enrich_dataframe


                    from tinvest.advanced_entry import classify_entry


                    from tinvest.valuation_engine import evaluate_stock_valuation


                    


                    df_rich = enrich_dataframe(idx_df.copy())


                    mom = analyze_momentum_divergence(idx_df)


                    signals = classify_entry(df_rich)


                    


                    has_signal = signals.get('entry_type', 'NONE') != 'NONE'


                    if has_signal:


                        val = evaluate_stock_valuation("INDEX", df_rich, signals)


                        sr = {"s1": val.get("s1", 0), "s2": val.get("s2", 0),


                              "r1": val.get("r1", 0), "r2": val.get("r2", 0)}


                    else:


                        sr = calculate_index_sr(df_rich)


                    


                    return {


                        "regime": analyze_market_index(idx_df, breadth_pct_ma20=breadth_ma20, breadth_pct_ma50=breadth_ma50, momentum_data=mom),


                        "momentum": mom,


                        "ichi": analyze_ichimoku(df_rich),


                        "vsa": analyze_vsa(df_rich),


                        "ma": analyze_ma_trend(df_rich),


                        "sr": sr,


                        "sr_source": "SIGNAL" if has_signal else "PIVOT",


                        "signals": signals,


                        "date": idx_df['Date'].iloc[-1].strftime("%Y-%m-%d") if 'Date' in idx_df.columns else "N/A"


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


                    sr_label = "Dựa trên tín hiệu mua" if sr_source == "SIGNAL" else "Dựa trên đỉnh/đáy lịch sử"


                    regime_label = regime_labels.get(res['regime'], res['regime'])


                    


                    txt = f"\n--- TỔNG QUAN {name} ({res['date']})"


                    txt += f"\n * TRẠNG THÁI: {regime_label}"


                    txt += f"\n * HÀNH ĐỘNG: {res['action']}"


                    txt += f"\n * KHÁNG CỰ (R): {sr['r1'] if sr['r1'] > 0 else 'N/A'} | {sr['r2'] if sr['r2'] > 0 else 'N/A'}"


                    txt += f"\n * HỖ TRỢ (S): {sr['s1'] if sr['s1'] > 0 else 'N/A'} | {sr['s2'] if sr['s2'] > 0 else 'N/A'}"


                    txt += f"\n   (S/R: {sr_label})"


                    


                    if res['ftd_active']: txt += f"\n   - FTD: Đang Kích Hoạt ({res.get('ftd_quality', 'N/A')})"


                    elif res['ra_day'] > 0: txt += f"\n   - Nỗ lực hồi phục (RA): Ngày thứ {res['ra_day']}"


                    


                    txt += f"\n   - Ngày Phân Phối: {res['distribution_count']} ngày"


                    txt += f"\n * VSA: {vsa['dominant']} | Ichi: {ichi['trend']} | MA: {ma['trend_label']}"


                    txt += f"\n * RSI: {mom['rsi_val']} | MACD: {mom['macd_val']}"


                    


                    sigs = res_dict.get('signals', {})


                    if sigs and sigs.get('entry_type') != "NONE":


                        txt += f"\n 🔥 TÍN HIỆU: {sigs['entry_type']} ({sigs['confidence']})"


                    


                    return txt





                vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), "VNINDEX")


                hn_key = next((k for k in self.data_dict.keys() if "HNX" in k or "HAINDEX" in k), "HNXINDEX")


                


                vn_full = analyze_full_index(self.data_dict.get(vn_key))


                hn_full = analyze_full_index(self.data_dict.get(hn_key))


                


                report = ["="*60, "     BÁO CÁO TOÀN CẢNH THỊ TRƯỜNG CHUNG (MARKET REGIME)", "="*60]


                report.append(f"\n1. ĐỘ RỘNG THỊ TRƯỜNG (BREADTH): {breadth_res['breadth_label']}")


                report.append(f" - Tổng mã quét: {breadth_res['total_scanned']}")


                report.append(f" - Tỷ lệ mã > MA20: {breadth_res.get('strong_stocks_ma20_pct', 'N/A')}%")


                report.append(f" - Tỷ lệ mã > MA50: {breadth_res['strong_stocks_pct']}%")


                


                report.append(format_index(vn_key, vn_full).replace("---", "2."))


                if hn_full: report.append(format_index(hn_key, hn_full).replace("---", "3."))


                    


                report.extend(["\n" + "="*60, "CHIẾN LƯỢC HÀNH ĐỘNG THEO TRẠNG THÁI:", "─"*60,


                               "- UPTREND: 100% tỷ trọng, MA20 > MA50 & Giá > MA50.",


                               "- UPTREND RỦI RO: Có phân phối hoặc MA20 < MA50. Chốt lời dần.",


                               "- HỒI PHỤC ỔN ĐỊNH: Có FTD & vượt MA20/Kijun. Tăng tỷ trọng 50-75%.",


                               "- HỒI PHỤC: Có FTD & vượt MA10. Thăm dò 10-20%.",


                               "- HỒI PHỤC YẾU: Có từ 3 phiên nỗ lực hồi phục. Theo dõi FTD.",


                               "- SIDEWAY: Đi ngang biên ±5% quanh MA50. Swing trade.",


                               "- SUY YẾU: Giá nằm dưới MA50. Co cụm danh mục.",


                               "- DOWNTREND: Thị trường giảm giá > 10%. Đứng ngoài."])


                


                self.log_sync("\n".join(report))


                


            except Exception as e:


                import traceback


                self.log_sync(f"\n❌ LỖI PHÂN TÍCH THỊ TRƯỜNG: {str(e)}\n{traceback.format_exc()}")


        


        import threading


        threading.Thread(target=analyze_task, daemon=True).start()





    def show_market_breadth(self):


        if getattr(self, 'market_breadth', None) is None or self.market_breadth.empty:


            from tkinter import messagebox


            messagebox.showwarning("Cảnh báo", "Dữ liệu độ rộng thị trường chưa sẵn sàng. Vui lòng nạp dữ liệu!")


            return


            


        try:


            import matplotlib.pyplot as plt


            import matplotlib.dates as mdates


        except ImportError:


            import sys


            import subprocess


            from tkinter import messagebox


            messagebox.showinfo("Đang Tự Cài Đặt", "Hệ thống đang cài 'matplotlib'...")


            try:


                subprocess.check_call([sys.executable, "-m", "pip", "install", "matplotlib"])


                import matplotlib.pyplot as plt


                import matplotlib.dates as mdates


            except Exception as e:


                messagebox.showerror("Lỗi", f"Không thể cài đặt matplotlib: {e}")


                return


            


        try:


            days = 504


            df_plot = self.market_breadth.tail(days).copy()


            if df_plot.empty: return


                


            dates = pd.to_datetime(df_plot.index)


            df_plot['%MA20_smooth'] = df_plot['%MA20'].rolling(window=5, min_periods=1).mean()


            df_plot['%MA50_smooth'] = df_plot['%MA50'].rolling(window=5, min_periods=1).mean()


            


            fig, ax1 = plt.subplots(figsize=(14, 8))
            
            # --- Primary Axis: Breadth (%) ---
            line1, = ax1.plot(dates, df_plot['%MA20_smooth'], color='#2196F3', linewidth=2, label='% Cổ phiếu > MA20')
            line2, = ax1.plot(dates, df_plot['%MA50_smooth'], color='#9C27B0', linewidth=2, label='% Cổ phiếu > MA50')
            
            # Add latest value annotations
            last_date = dates[-1]
            val20 = df_plot['%MA20_smooth'].iloc[-1]
            val50 = df_plot['%MA50_smooth'].iloc[-1]
            
            ax1.annotate(f" {val20:.1f}%", xy=(last_date, val20), xytext=(8, -5), textcoords='offset points', 
                         color='#1976D2', fontweight='bold', fontsize=11)
            ax1.annotate(f" {val50:.1f}%", xy=(last_date, val50), xytext=(8, 5), textcoords='offset points', 
                         color='#7B1FA2', fontweight='bold', fontsize=11)

            ax1.set_title('BIỂU ĐỒ ĐỘ RỘNG THỊ TRƯỜNG & VNINDEX', fontsize=14, fontweight='bold', pad=20)
            ax1.set_xlabel('Thời Gian')
            ax1.set_ylabel('Tỉ Lệ Độ Rộng (%)', fontsize=10, fontweight='bold')
            ax1.set_ylim(0, 100)
            ax1.grid(True, linestyle='--', alpha=0.4)

            # --- Secondary Axis: VNINDEX Price ---
            vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), "VNINDEX")
            df_vn = self.data_dict.get(vn_key)
            if df_vn is not None and not df_vn.empty:
                # Align VNINDEX data with the plot dataframe dates
                df_vn_plot = df_vn.loc[df_vn.index.isin(df_plot.index)]
                if not df_vn_plot.empty:
                    ax2 = ax1.twinx()
                    line3, = ax2.plot(dates, df_vn_plot['Close'], color='grey', alpha=0.35, 
                                     linestyle='--', linewidth=1.5, label='VNINDEX (Price)')
                    ax2.set_ylabel('Điểm số VNINDEX', color='grey', fontsize=10)
                    ax2.tick_params(axis='y', labelcolor='grey')
                    
                    # Combine legends
                    lines = [line1, line2, line3]
                    labels = [l.get_label() for l in lines]
                    ax1.legend(lines, labels, loc='upper left', frameon=True, shadow=True)
            else:
                ax1.legend(loc='upper left', frameon=True, shadow=True)

            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m/%Y'))
            fig.autofmt_xdate()
            
            plt.tight_layout()
            plt.show()


        except Exception as e:


            from tkinter import messagebox


            messagebox.showerror("Lỗi biểu đồ", f"Lỗi khi vẽ: {str(e)}")





if __name__ == "__main__":


    root = tk.Tk()


    app = TinvestApp(root)


    root.mainloop()


