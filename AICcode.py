"""


AIC code = AI + cơm! Desktop App


Giao diện người dùng cho hệ thống phân tích AIC code = AI + cơm!


"""


import tkinter as tk
import logging
logger = logging.getLogger(__name__)


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


        from tinvest.state_engine import evaluate_state_rules
        state_rules = evaluate_state_rules(df_rich)
        
        return ticker, {
            "df": df_rich,
            "ichi": ichi,
            "vsa": vsa,
            "adv": adv,
            "accum": accum,
            "ma_trend": ma_trend,
            "valuation": val,
            "state_rules": state_rules
        }


    except Exception:


        return ticker, None





def analyze_batch_worker(batch):
    """Xử lý một nhóm (batch) mã cổ phiếu trong một tiến trình duy nhất."""
    results = []
    for item in batch:
        results.append(analyze_ticker_worker(item))
    return results

def load_cache_worker(args):
    """
    Worker for ThreadPoolExecutor to load data from disk.
    Args: (ticker, storage_instance)
    """
    ticker, storage = args
    try:
        df = storage.load_ticker_data(ticker)
        if df is not None:
            analysis = storage.load_latest_analysis(ticker)
            if analysis:
                analysis['df'] = df
            return ticker, df, analysis
    except Exception:
        pass
    return ticker, None, None





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

        btn_cleanup = tk.Button(frame_btns, text="🧹 Dọn dẹp", command=self.cleanup_storage, bg="#FF5722", fg="white", font=("Arial", 9, "bold"), padx=8)
        btn_cleanup.pack(side=tk.RIGHT, padx=2)





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





        btn_wait = tk.Button(frame_signals_2, text="☁️ Danh mục UPCLOUD", command=lambda: self.run_advanced_scanner("UPCLOUD"), bg="#1E90FF", fg="white", font=("Arial", 10, "bold"))


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

    def cleanup_storage(self):
        """Physically delete junk files from disk based on the registry."""
        registry = self.storage.get_active_registry()
        if not registry:
            messagebox.showwarning("Cảnh báo", "Chưa có Registry (Whitelist). Vui lòng Chạy 'Update' trước để hệ thống xác định danh sách mã niêm yết hiện tại.")
            return
            
        junk_tickers = self.storage.cleanup_inactive_files(dry_run=True)
        if not junk_tickers:
            messagebox.showinfo("Thông báo", "Tuyệt vời! Dữ liệu của bạn đã sạch sẽ, không tìm thấy mã rác nào.")
            return
            
        confirm = messagebox.askyesno("Xác nhận dọn dẹp", f"Tìm thấy {len(junk_tickers)} mã cũ/rác (không còn niêm yết hoặc file rác).\n\nBạn có chắc chắn muốn XÓA VĨNH VIỄN các file này khỏi ổ cứng để tăng tốc hệ thống không?")
        if confirm:
            deleted = self.storage.cleanup_inactive_files(dry_run=False)
            messagebox.showinfo("Hoàn tất", f"Đã xóa thành công {len(deleted)} mã rác. Hãy 'Load Cache' lại để thấy sự thay đổi.")
            self.load_from_cache()





    def _load_from_cache_bg(self):


        try:


            tickers = self.storage.get_all_tickers()


            if not tickers:


                self.log_sync("Chưa có dữ liệu trong cache. Vui lòng bấm 'Cập Nhật Vietstock' hoặc 'Nạp Thêm CSV'.")


                return





            self.data_dict = {}


            self.analysis_cache = {}


            


            registry = self.storage.get_active_registry()
            all_storage_tickers = tickers # Original list on disk
            if registry:
                filtered = [t for t in tickers if t in registry]
                self.log_sync(f"[*] Registry tìm thấy {len(registry)} mã. Lọc bỏ {len(tickers)-len(filtered)} mã cũ/rác.")
                tickers = filtered
            
            total = len(tickers)
            self.log_sync(f"[*] Đang nạp {total} mã cổ phiếu bằng đa luồng (8-16 workers)...")
            
            # --- PARALLEL LOADING ---
            from concurrent.futures import ThreadPoolExecutor, as_completed
            num_workers = min(16, (os.cpu_count() or 4) * 2)
            
            loaded_count = 0
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                tasks = [(t, self.storage) for t in tickers]
                futures = {executor.submit(load_cache_worker, tea): tea[0] for tea in tasks}
                
                for future in as_completed(futures):
                    t, df, analysis = future.result()
                    if df is not None:
                        self.data_dict[t] = df
                        if analysis:
                            self.analysis_cache[t] = analysis
                    
                    loaded_count += 1
                    if loaded_count % 100 == 0 or loaded_count == total:
                        self.log_sync(f" ---> Tiến trình: Đã nạp {loaded_count}/{total} mã cổ phiếu...")

            # --- FINISH ---
            self._update_breadth_from_cache()
            self.root.after(0, self.lbl_file.config, {"text": f"Dữ liệu: {len(self.analysis_cache)} mã", "fg": "blue"})
            self.log_sync(f"✅ Hoàn tất! Đã nạp thành công {len(self.analysis_cache)} mã.")
            
            # Check for physical cleanup
            if registry and len(all_storage_tickers) > len(tickers) + 50:
                self.log_sync(f"\n⚠️ LƯU Ý: Phát hiện {len(all_storage_tickers) - len(tickers)} mã 'rác' trong ổ cứng.")
                self.log_sync("Hệ thống đã tự động lọc bỏ khi nạp. Bạn có thể nhấn 'Xóa mã cũ' để dọn dẹp ổ cứng.")

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
                    
                    # Cap nhat Registry neu day la ngay moi nhat va du lieu "sach" (>1000 ma)
                    if total_p1 > 1000 and d == missing_dates[-1]:
                        all_tickers = df_day['Ticker'].unique().tolist()
                        self.storage.save_active_registry(all_tickers)
                        self.log_sync(f"   [*] Đã cập nhật Registry: {len(all_tickers)} mã niêm yết.")


                    


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
            self.log_sync(f"BÁO CÁO CHI TIẾT MÃ: {ticker}\n" + report, clear=True)


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


                # Flexible key mapping for signal and accumulation
                res = data.get("adv") or data.get("advanced_entry") or data.get("entry_signal") or {}
                accum = data.get("accum") or data.get("accumulation") or {}


                # Ensure backward compatibility for valuation key
                val = data.get("valuation") or data.get("val") or {}


                


                df = data.get("df")
                if df is None or (hasattr(df, 'empty') and df.empty):
                    continue


                avg_vol_20 = df["Volume"].tail(20).mean() if len(df) >= 20 else df["Volume"].mean()





                match = False


                if entry_target == "ACCUMULATION":


                    if accum["is_accumulation"]:


                        match = True


                        size = "N/A"


                        conf = accum["base_quality"]


                        flags = "Ready to break" if accum["ready_to_break"] else ", ".join(accum["notes"])


                elif entry_target == "PERFECT_MA":


                    ma_trend = data.get("ma_trend") or data.get("ma") or {}


                    if ma_trend.get("is_perfect_uptrend"):


                        match = True


                        size = "N/A"


                        conf = "HIGH"


                        flags = "MA10 > MA20 > MA50 > 100 > 200 (Giá > MA20 & Hỗ trợ MA50)"


                elif entry_target == "TRADEABLE":
                    action_str = val.get("action", "")
                    sr = data.get("state_rules", {})
                    sr_sig = sr.get("signal", "NONE")
                    sr_pri = sr.get("primary", "")
                    sr_avoid = sr.get("avoid_entry", False)
                    sr_conf = int(sr.get("confidence", 0))
                    
                    opp_score = val.get("opp_score", 0)
                    risk_score = val.get("risk_score", 0)
                    
                    # Dieu kien mua NGHIEM NGAT hon de loc co phieu "Mua duoc luon":
                    # 1) Opportunity Score cao (>= 50) va Risk Score thap (< 45)
                    # 2) Primary State phai la TANG hoac bat dau TANG/Nen chat
                    # 3) Khong bi bo loc rui ro chan
                    # 4) Gia khong vuot qua 5% so voi diem mua ly tuong (Buy Zone)
                    
                    ideal_price = val.get("price", 0)
                    current_price = df['Close'].iloc[-1]
                    in_buy_zone = (current_price <= ideal_price * 1.05) if ideal_price > 0 else False
                    
                    trend_ok = sr_pri in ["UPTREND", "UPTREND_START", "WEAK_UPTREND", "TRANSITION", "SQUEEZE"]
                    
                    # Bo loc tong hop ni l?ng theo yu c?u
                    if not sr_avoid and trend_ok and sr_conf >= 1 and opp_score >= 50 and risk_score < 45 and in_buy_zone:
                        match = True
                        size = res.get("position_size", "N/A")
                        conf = f"STATE:{sr_conf} | OPP:{opp_score}"
                        flags = f"Buy Zone ({(current_price/ideal_price-1)*100:+.1f}%) | {sr_sig} | {sr_pri}"


                elif entry_target == "UPCLOUD":
                    # Criteria:
                    # 1. Price > Cloud top (SpanA, SpanB)
                    # 2. Future Cloud is Green (SpanA_ahead > SpanB_ahead)
                    # 3. Tenkan > Kijun
                    # 4. MA10 > MA20
                    
                    last = df.iloc[-1]
                    current_price = last['Close']
                    span_a = last.get('SpanA', 0)
                    span_b = last.get('SpanB', 0)
                    tenkan = last.get('Tenkan', 0)
                    kijun = last.get('Kijun', 0)
                    ma10 = last.get('MA10', 0)
                    ma20 = last.get('MA20', 0)
                    
                    # Future Cloud calculation (plotted 26 days ahead based on today's data)
                    future_span_a = (tenkan + kijun) / 2
                    h52 = df['High'].iloc[-52:].max()
                    l52 = df['Low'].iloc[-52:].min()
                    future_span_b = (h52 + l52) / 2
                    
                    c1 = (current_price > span_a) and (current_price > span_b) if span_a > 0 else False
                    c2 = (future_span_a > future_span_b)
                    c3 = (tenkan > kijun)
                    c4 = (ma10 > ma20)
                    
                    if c1 and c2 and c3 and c4:
                        match = True
                        size = "N/A"
                        conf = "ICHIMOKU"
                        flags = "UPCLOUD (Price > Cloud | Mây TL Xanh | T>K | MA10>MA20)"
                elif entry_target == "WHITE_ADX":
                    adx_color = str(df['ADX_Color'].iloc[-1]).upper() if 'ADX_Color' in df.columns else "N/A"
                    if adx_color == "WHITE":
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


                    # Skip if risk is too high or explicitly invalid data
                    risk_limit = 20.0 if entry_target == "WHITE_ADX" else 15.0
                    # For compatibility, if 'is_valid' is missing (None), we treat it as True
                    # Skip if risk is too high or explicitly invalid data
                    risk_limit = 20.0 if entry_target == "WHITE_ADX" else 15.0
                    # For compatibility, if 'is_valid' is missing (None), we treat it as True
                    if val.get("is_valid", True) is False or val.get("risk_pct", 0) > risk_limit:
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


                    val_score = val.get("risk_score", 0)


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


                


                # Take last 100 days for clearer visibility


                df_plot = df_rich.tail(100).copy()


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


                


                hist_cloud = df_rich[['Date', 'SpanA', 'SpanB']].tail(100).copy()


                


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





                # Fetch analysis (RE-CALCULATE to ensure chart is in sync with latest logic)
                from tinvest.analyzer import analyze_stock
                analysis_fresh = analyze_stock(ticker, df_rich)
                val = analysis_fresh.get('valuation', {})
                adv = analysis_fresh.get('adv', {})
                analysis = analysis_fresh # Use fresh for the rest of drawing too


                


                # Create fig (4 subplots for Price, Volume, RSI, ADX)


                fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [5, 1.2, 1.2, 1.5]}, sharex=True)


                plt.subplots_adjust(hspace=0.08, bottom=0.1)


                


                # --- MAP X AXIS TO ORDINAL SCALAR TO PREVENT GAPS ---
                x_idx_plot = np.arange(len(df_plot))
                x_idx_ext = np.arange(len(df_ext))
                
                date_labels = df_ext['Date'].dt.strftime('%d/%m').tolist()
                def format_date(x, pos):
                    try:
                        idx = int(round(x))
                        if 0 <= idx < len(date_labels):
                            return date_labels[idx]
                    except:
                        pass
                    return ""
                
                # Plot Candlesticks...
                up_mask = df_plot['Close'] >= df_plot['Open']
                down_mask = df_plot['Close'] < df_plot['Open']
                ax1.bar(x_idx_plot[up_mask], df_plot.loc[up_mask, 'Close'] - df_plot.loc[up_mask, 'Open'], bottom=df_plot.loc[up_mask, 'Open'], color='green', width=0.6, alpha=0.8)
                ax1.bar(x_idx_plot[down_mask], df_plot.loc[down_mask, 'Open'] - df_plot.loc[down_mask, 'Close'], bottom=df_plot.loc[down_mask, 'Close'], color='red', width=0.6, alpha=0.8)
                ax1.vlines(x_idx_plot[up_mask], df_plot.loc[up_mask, 'Low'], df_plot.loc[up_mask, 'High'], color='green', linewidth=1)
                ax1.vlines(x_idx_plot[down_mask], df_plot.loc[down_mask, 'Low'], df_plot.loc[down_mask, 'High'], color='red', linewidth=1)

                # Plot MAs...
                ma_styles = [('MA10', 'black', 'MA10', 2), ('MA20', 'green', 'MA20', 2), ('MA50', 'brown', 'MA50', 1)]
                for ma_col, color, label, lw in ma_styles:
                    if ma_col in df_plot.columns:
                        ax1.plot(x_idx_plot, df_plot[ma_col], label=label, color=color, linewidth=lw, alpha=0.8)

                # Plot Ichimoku Cloud
                ax1.fill_between(x_idx_ext, df_total_cloud['SpanA'], df_total_cloud['SpanB'], 
                                 where=(df_total_cloud['SpanA'] >= df_total_cloud['SpanB']), color='lime', alpha=0.3, label='Kumo Green')
                ax1.fill_between(x_idx_ext, df_total_cloud['SpanA'], df_total_cloud['SpanB'], 
                                 where=(df_total_cloud['SpanA'] < df_total_cloud['SpanB']), color='red', alpha=0.3, label='Kumo Red')
                    
                if 'Tenkan' in df_plot.columns:
                    ax1.plot(x_idx_plot, df_plot['Tenkan'], color='blue', label='Tenkan', linewidth=1.0, alpha=0.9)
                if 'Kijun' in df_plot.columns:
                    ax1.plot(x_idx_plot, df_plot['Kijun'], color='red', label='Kijun', linewidth=1.0, alpha=0.9)
                if 'Kijun65' in df_plot.columns:
                    ax1.plot(x_idx_plot, df_plot['Kijun65'], color='orange', linestyle='--', label='Dao 65', linewidth=2.0, alpha=0.8)

                # Scaling: Limit Y axis to price area
                p_min, p_max = df_plot['Low'].min(), df_plot['High'].max()
                ax1.set_ylim(p_min * 0.95, p_max * 1.05)
                
                # Plot S1, S2, R1, R2 lines...
                last_idx = x_idx_plot[-1]
                future_idx = last_idx + 22
                
                # Formatting helper and Title
                is_index = ticker.upper().endswith("INDEX") or "VN30" in ticker.upper()
                fmt = "{:,.0f}" if is_index else "{:,.2f}"
                
                # --- Top Title with Logo ---
                logo_path = r"C:\Users\COMPUTER\Desktop\Vector logo.png"
                logo_found = False
                try:
                    if os.path.exists(logo_path):
                        from matplotlib.offsetbox import OffsetImage, AnnotationBbox
                        import matplotlib.image as mpimg
                        img = mpimg.imread(logo_path)
                        imagebox = OffsetImage(img, zoom=0.15) # Adjust zoom as needed
                        ab = AnnotationBbox(imagebox, (0.4, 0.96), frameon=False, xycoords='figure fraction')
                        fig.add_artist(ab)
                        fig.text(0.45, 0.96, "=AI+CƠM!", ha="left", va="center", fontsize=22, fontweight='bold', color='black')
                        logo_found = True
                except Exception as e:
                    logger.error(f"Error loading logo: {e}")
                
                if not logo_found:
                    fig.text(0.5, 0.98, "AIC CODE = AI + CƠM!", ha="center", va="top", fontsize=20, fontweight='bold', color='black')
                
                ax1.set_title(f"Technical Analysis Report:", fontsize=12, style='italic', color='#555555', pad=10, loc='center')
                ax1.text(0.5, 1.12, ticker, transform=ax1.transAxes, fontsize=24, fontweight='bold', color='darkblue', ha='center', va='bottom')

                # Current Price Marker
                current_price = df_plot['Close'].iloc[-1]
                ax1.hlines(current_price, xmin=last_idx, xmax=future_idx, color='black', linestyle='-', linewidth=2.0, alpha=0.8)
                ax1.text(future_idx, current_price, f" {fmt.format(current_price)}", color='black', fontsize=10, fontweight='bold', va='center', ha='left', bbox=dict(facecolor='yellow', alpha=0.8, edgecolor='none', pad=1))
                
                if val:
                    sr_config = [('s1', 'green', 'S1'), ('s2', 'darkgreen', 'S2'), 
                                 ('r1', 'red', 'R1'), ('r2', 'darkred', 'R2')]
                    for sr_key, color, lbl in sr_config:
                        level = val.get(sr_key, 0)
                        if level > 0:
                            ax1.hlines(level, xmin=last_idx, xmax=future_idx, color=color, linestyle='--', alpha=0.8, linewidth=1.5)
                            ax1.text(future_idx, level, f" {lbl}: {fmt.format(level)}", color=color, 
                                     fontsize=9, fontweight='bold', va='center', ha='left')

                # --- Summary Assessment Overlay ---
                sr = analysis.get('state_rules', {})
                sr_pri = sr.get('primary', 'N/A')
                sr_sec = sr.get('secondary', 'N/A')
                opp_score = val.get('opp_score', 0)
                risk_score = val.get('risk_score', 0)
                report_date = df_plot['Date'].iloc[-1].strftime('%d/%m/%Y')
                
                summary_text = (
                    f"TÓM LƯỢC NHẬN ĐỊNH ({report_date})\n"
                    f"● Trạng thái: {sr_pri}\n"
                    f"● Vận động: {sr_sec}\n"
                    f"● Opp Score: {opp_score}/100 | Risk: {risk_score}/100\n"
                    f"● Xu hướng: {'TĂNG' if opp_score > 50 else 'THEO DÕI' if opp_score > 30 else 'YẾU'}"
                )
                
                # Move summary box down to avoid Legend overlap
                ax1.text(0.01, 0.75, summary_text, transform=ax1.transAxes, fontsize=10,
                         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='darkblue'))


                


                # Signals... (up to 3 arrows)
                from tinvest.advanced_entry import _eval_day
                buy_signals = []
                for real_idx in df_plot.index.tolist():
                    rel_idx = -(len(df_rich) - df_rich.index.get_loc(real_idx))
                    sig = _eval_day(df_rich, rel_idx)
                    if sig and sig.get('type') in ["EARLY", "ADD_1", "ADD_2", "STRONG"]:
                        buy_signals.append({'date': df_rich['Date'].loc[real_idx], 'type': sig['type'], 
                                           'source': sig.get('details', {}).get('source', 'N/A'), 'price': df_rich['Low'].loc[real_idx]})

                buy_signals = sorted(buy_signals, key=lambda x: x['date'], reverse=True)[:3]
                annotation_text = "3 ĐIỂM MUA GẦN NHẤT:\n\n"
                for i, b in enumerate(buy_signals):
                    matches = np.where(df_plot['Date'] == b['date'])[0]
                    if len(matches) > 0:
                        pos = matches[0]
                        ax1.plot(pos, b['price'] * 0.98, '^', markersize=12, color='lime', markeredgecolor='green')
                        annotation_text += f" • #{i+1}: {b['date'].strftime('%d/%m')} - {b['type']} ({b['source']})\n\n"

                if buy_signals:
                    fig.text(0.1, 0.02, annotation_text, fontsize=10, color='darkgreen', 
                             linespacing=1.8, bbox=dict(facecolor='white', alpha=0.9, edgecolor='lime', pad=5))

                # Volume...
                ax2.bar(x_idx_plot, df_plot['Volume'], 
                        color=np.where(df_plot['Close'] >= df_plot['Open'], 'green', 'red'), alpha=0.5, width=0.6)
                if 'VolMA20' in df_plot.columns:
                    ax2.plot(x_idx_plot, df_plot['VolMA20'], color='blue', alpha=0.6)

                # --- RSI Subplot ---
                if 'RSI' in df_plot.columns:
                    ax3.plot(x_idx_plot, df_plot['RSI'], color='purple', linewidth=1.5, label='RSI (14)')
                    ax3.axhline(70, color='red', linestyle='--', alpha=0.5)
                    ax3.axhline(50, color='gray', linestyle='-.', alpha=0.5)
                    ax3.axhline(30, color='green', linestyle='--', alpha=0.5)
                    ax3.set_ylabel('RSI', fontweight='bold', fontsize=9)
                    ax3.set_ylim(10, 90)
                    ax3.legend(loc='upper left', fontsize=8)
                    ax3.grid(True, linestyle='--', alpha=0.3)
                else:
                    ax3.set_visible(False)

                # --- MACD Subplot ---
                if 'MACD' in df_plot.columns and 'MACD_Signal' in df_plot.columns:
                    ax4.plot(x_idx_plot, df_plot['MACD'], color='blue', linewidth=1.5, label='MACD')
                    ax4.plot(x_idx_plot, df_plot['MACD_Signal'], color='orange', linewidth=1.5, label='Signal')
                    if 'MACD_Hist' in df_plot.columns:
                        colors = np.where(df_plot['MACD_Hist'] >= 0, 'green', 'red')
                        ax4.bar(x_idx_plot, df_plot['MACD_Hist'], color=colors, alpha=0.6, width=0.6)
                    ax4.axhline(0, color='black', linestyle='-', linewidth=1, alpha=0.5)
                    ax4.set_ylabel('MACD', fontweight='bold', fontsize=9)
                    ax4.legend(loc='upper left', fontsize=8, ncol=3)
                    ax4.grid(True, linestyle='--', alpha=0.3)
                else:
                    ax4.set_visible(False)

                # Final Layout
                ax1.grid(True, linestyle='--', alpha=0.3)
                ax1.tick_params(labelright=True) # Ensure right-side price labels
                ax1.legend(loc='upper left', fontsize=9, ncol=4)
                
                # Use FuncFormatter to map ordinal x back to Dates
                import matplotlib.ticker as ticker_lib
                ax4.xaxis.set_major_formatter(ticker_lib.FuncFormatter(format_date))
                
                # Make sure the x limits are bounded by the total ordinal length
                ax1.set_xlim(0, len(x_idx_ext) + 2)
                ax2.grid(True, linestyle='--', alpha=0.3)
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
                    val = evaluate_stock_valuation("INDEX", df_rich, signals)
                    sr = {"s1": val.get("s1", 0), "s2": val.get("s2", 0),
                          "r1": val.get("r1", 0), "r2": val.get("r2", 0)}

                    # State Engine cho Index
                    from tinvest.state_engine import evaluate_state_rules
                    state_rules = evaluate_state_rules(df_rich)

                    res_regime = analyze_market_index(idx_df, breadth_pct_ma20=breadth_ma20, breadth_pct_ma50=breadth_ma50, momentum_data=mom)
                    res_regime['price'] = float(idx_df['Close'].iloc[-1])

                    return {
                        "regime": res_regime,
                        "momentum": mom,
                        "ichi": analyze_ichimoku(df_rich),
                        "vsa": analyze_vsa(df_rich),
                        "ma": analyze_ma_trend(df_rich),
                        "sr": sr,
                        "sr_source": "SIGNAL" if has_signal else "PIVOT",
                        "signals": signals,
                        "valuation": val,
                        "state_rules": state_rules,
                        "date": idx_df['Date'].iloc[-1].strftime("%Y-%m-%d") if 'Date' in idx_df.columns else "N/A"
                    }





                def format_index(name, res_dict, prefix=""):


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


                    


                    txt = f"\n{prefix}THỊ TRƯỜNG {name} ({res['date']})"
                    txt += f"\n * CHỈ SỐ: {res['price']:,.2f}"


                    txt += f"\n * TRẠNG THÁI: {regime_label}"


                    txt += f"\n * HÀNH ĐỘNG: {res['action']}"


                    txt += f"\n * KHÁNG CỰ (R): {sr['r1'] if sr['r1'] > 0 else 'N/A'} | {sr['r2'] if sr['r2'] > 0 else 'N/A'}"


                    txt += f"\n * HỖ TRỢ (S): {sr['s1'] if sr['s1'] > 0 else 'N/A'} | {sr['s2'] if sr['s2'] > 0 else 'N/A'}"


                    txt += f"\n   (S/R: {sr_label})"


                    


                    if res['ftd_active']: 
                        ftd_str = res.get('ftd_date', 'N/A')
                        txt += f"\n   - XÁC NHẬN FTD: Đang Kích Hoạt (Từ phiên {ftd_str} - {res.get('ftd_quality', 'N/A')})"


                    txt += f"\n   - Nỗ lực hồi phục (RA) : Ngày thứ {res['ra_day']}" if res['ra_day'] > 0 else ""
                    txt += f"\n   - Ngày Phân Phối      : {res['distribution_count']} ngày\n"
                    
                    diag = res_dict.get('valuation', {}).get('tech_health', {}).get('diagnostics', {})
                    if diag:
                        ma_d = diag.get('ma', {})
                        ichi_d = diag.get('ichimoku', {})
                        rsi_d = diag.get('rsi', {})
                        macd_d = diag.get('macd', {})
                        adx_d = diag.get('adx', {})
                        
                        txt += "\n [2.1 CHẨN ĐOÁN CHỈ BÁO THỊ TRƯỜNG]"
                        txt += f"\n   ● [MA] {ma_d.get('status', '')}"
                        txt += f"\n   ● [MA Hành động] {ma_d.get('action', '')}"
                        txt += f"\n   ● [Ichimoku] {ichi_d.get('status', '')}"
                        txt += f"\n   ● [RSI Setup] {rsi_d.get('status', '')}"
                        txt += f"\n   [MACD Setup] {macd_d.get('status', '')}"
                        txt += f"\n   ● [ADX Setup] {adx_d.get('status', '')}\n"
                    else:
                        txt += f"\n * VSA: {vsa['dominant']} | Ichi: {ichi['trend']} | MA: {ma['trend_label']}"
                        txt += f"\n * RSI: {mom['rsi_val']} | MACD: {mom['macd_val']}\n"
                    
                    sigs = res_dict.get('signals', {})
                    if sigs and sigs.get('entry_type') != "NONE":
                        txt += f"\n 🔥 TÍN HIỆU: {sigs['entry_type']} ({sigs['confidence']})"
                    
                    # === STATE ENGINE: DAC DIEM TRANG THAI THI TRUONG ===
                    st = res_dict.get('state_rules', {})
                    alloc = "10-30%" # Default
                    alloc_note = "Chưa xác định rõ"
                    if st:
                        pri_map = {"UPTREND": "Sóng Tăng mạnh", "DOWNTREND": "Sóng Giảm mạnh", "UPTREND_START": "Vừa bứt phá vào sóng Tăng", "DOWNTREND_START": "Vừa gãy nền vào sóng Giảm", "WEAK_UPTREND": "Tăng nhưng yếu dần", "WEAK_DOWNTREND": "Giảm nhẹ (đà rơi chậm lại)", "RECOVERY": "Giai đoạn HỒI PHỤC", "RANGE": "Đi biên ngang", "SQUEEZE": "Nén chặt biên hẹp", "NEUTRAL": "Trạng thái Trung tính", "SIDEWAY": "Đi ngang"}
                        sec_map = {"PULLBACK": "Nhịp kéo ngược (chỉnh lành mạnh)", "FAILED_PULLBACK": "Kéo ngược thất bại (thủng nền)", "EXHAUSTION": "Đuối sức (nguy cơ đảo chiều)", "REVERSAL_BUILD": "Xây nền đảo chiều đáy", "ROLL_OVER": "Xác nhận gãy", "ACCUMULATION": "Gom hàng bám nền", "DISTRIBUTION": "Phân phối", "TRAP": "Bẫy giá (lùa gà)", "UNDER_PRESSURE": "Áp lực bán (Tiệm cận hỗ trợ)", "NORMAL": "Bình thường"}
                        sig_map = {"BREAKOUT_BUY": "MUA BREAKOUT", "PULLBACK_BUY": "MUA PULLBACK", "TREND_FOLLOW": "ÔM TIẾP", "REVERSAL_BUY": "MUA BẮT ĐÁY", "TAKE_PROFIT": "CHỐT LÃI", "EXIT_OR_SHORT": "THOÁT HÀNG", "EXIT_FAST": "CHẠY NGAY", "SHORT": "Đứng ngoài", "NO_TRADE": "CẤM MUA", "NONE": "Chưa có tín hiệu"}
                        
                        st_pri = pri_map.get(st.get('primary', ''), st.get('primary', 'N/A'))
                        st_sec = sec_map.get(st.get('secondary', ''), st.get('secondary', 'N/A'))
                        st_sig = sig_map.get(st.get('signal', ''), st.get('signal', 'N/A'))
                        st_conf = int(st.get('confidence', 0))
                        st_avoid = st.get('avoid_entry', False)
                        
                        if st_conf >= 3: st_win = "Tốt (>= 70%)"
                        elif st_conf == 2: st_win = "Khá (~ 60%)"
                        elif st_conf >= 0: st_win = "Trung bình (~ 50%)"
                        else: st_win = "Thấp (< 50%)"
                        
                        # Ty trong khuyen nghi: ket hop State Engine + FTD + Phan phoi
                        st_pri_raw = st.get('primary', '')
                        ftd_on = res['ftd_active']
                        dist_n = res.get('distribution_count', 0)
                        
                        if st_pri_raw in ['UPTREND', 'UPTREND_START']:
                            if ftd_on and dist_n <= 2:
                                alloc = "80-100%"
                                alloc_note = "Xu hướng mạnh, FTD xác nhận, phân phối ít -> ALL IN được"
                            elif ftd_on and dist_n > 2:
                                alloc = "60-80%"
                                alloc_note = "Xu hướng tăng nhưng phân phối đang tăng -> vẫn giữ tỷ trọng cao nhưng sẵn sàng hạ"
                            else:
                                alloc = "60-80%"
                                alloc_note = "Xu hướng tăng nhưng chưa có FTD xác nhận -> chưa nên full"
                        elif st_pri_raw == 'WEAK_UPTREND':
                            if ftd_on:
                                alloc = "50-70%"
                                alloc_note = "Tăng yếu dần nhưng FTD còn sống -> canh giữ, giảm dần nếu chớm gãy"
                            else:
                                alloc = "30-50%"
                                alloc_note = "Tăng yếu dần, không có FTD -> cẩn thận chuyển giao"
                        elif st_pri_raw in ['RANGE', 'SQUEEZE', 'SIDEWAY', 'NEUTRAL']:
                            if ftd_on:
                                alloc = "50-70%"
                                alloc_note = "Đang tích lũy/chuyển giao trong nhịp hồi có FTD -> ưu tiên nắm giữ cổ phiếu Leader"
                            else:
                                alloc = "20-40%"
                                alloc_note = "Chưa rõ xu hướng, đang tích lũy/trung tính -> giữ tiền mặt chờ xác nhận"
                        elif st_pri_raw == 'WEAK_DOWNTREND':
                            if ftd_on:
                                alloc = "40-60%"
                                alloc_note = "Nhịp điều chỉnh/nghỉ chân trong đà hồi phục có FTD -> CƠ HỘI GOM HÀNG"
                            elif dist_n >= 3:
                                alloc = "0-15%"
                                alloc_note = "Giảm nhẹ + phân phối nhiều -> RỦI RO CAO, BÁN HẠ TỶ TRỌNG gấp"
                            else:
                                alloc = "15-30%"
                                alloc_note = "Điều chỉnh bình thường -> giữ ít, chờ xem có giữ nền không"
                        elif st_pri_raw in ['DOWNTREND', 'DOWNTREND_START']:
                            alloc = "0-10%"
                            alloc_note = "Gãy xu hướng xác nhận -> BÁN SẠCH, RA NGOÀI"
                        elif st_pri_raw == 'RECOVERY':
                            if ftd_on:
                                alloc = "50-75%"
                                alloc_note = "Hồi phục ổn định có FTD -> ưu tiên nắm giữ & quan sát điểm gia tăng"
                            else:
                                alloc = "20-40%"
                                alloc_note = "Hồi phục kỹ thuật, chưa có FTD -> chỉ nên test tỷ trọng nhỏ"
                        else:
                            # Unify with regime if possible
                            reg = res['regime']
                            if reg == "STABLE_RECOVERY":
                                alloc, alloc_note = "50-75%", "Hồi phục ổn định trên MA20"
                            elif reg == "RECOVERY":
                                alloc, alloc_note = "30-50%", "Đang nỗ lực hồi phục"
                            else:
                                alloc = "10-30%"
                                alloc_note = "Chưa xác định rõ -> giữ ít phòng thủ"
                        
                        # Override boi avoid
                        if st_avoid:
                            alloc = "0-10%"
                            alloc_note = "Bộ Lọc Rủi Ro đang BẬT -> CẤM MUA MỚI"
                        
                        m = st.get('metrics', {})
                        
                        txt += "\n\n [2.2 ĐẶC ĐIỂM TRẠNG THÁI THỊ TRƯỜNG (ROBOT)]"
                        txt += f"\n   ● Xu Hướng Cốt Lõi    : {st_pri}"
                        txt += f"\n   ● Hành Vi Vận Động     : {st_sec}"
                        txt += f"\n   ● Tín Hiệu Khuyến Nghị: {st_sig}"
                        txt += f"\n   ● Xác Suất Thắng      : {st_win} (Hệ số: {st_conf})"
                        txt += f"\n   ● Tỷ Trọng Khuyên     : {alloc} cổ phiếu ({alloc_note})"
                        if m:
                            txt += f"\n   ● ADX: {m.get('adx',0):.1f} | MACD Hist: {m.get('hist',0):.2f} | Vol Spike: {m.get('vol_spike', False)} | Trend Bias: {m.get('trend_bias', 0)}"
                    
                    txt += "\n\n 🎯 TỔNG KẾT CHIẾN LƯỢC TỪ AI:"
                    reg = res['regime']
                    s1_val = f"{sr['s1']:,.2f}" if sr['s1'] > 0 else 'N/A'
                    s2_val = f"{sr['s2']:,.2f}" if sr['s2'] > 0 else 'N/A'
                    r1_val = f"{sr['r1']:,.2f}" if sr['r1'] > 0 else 'N/A'
                    r2_val = f"{sr['r2']:,.2f}" if sr['r2'] > 0 else 'N/A'
                    dist_count = res.get('distribution_count', 0)
                    ra_day = res.get('ra_day', 0)
                    ftd_quality = res.get('ftd_quality', 'N/A')
                    
                    # Tinh SL cho Index dua tren S1
                    sl_idx = f"{sr['s1'] * 0.99:,.2f}" if sr['s1'] > 0 else 'N/A'
                    
                    if res['ftd_active']:
                        if reg in ["UPTREND", "STABLE_RECOVERY"]:
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - FTD XÁC NHẬN + ĐỒNG THUẬN TĂNG. MÔI TRƯỜNG THUẬN LỢI."
                            txt += f"\n     - Phân Bổ Tỷ Trọng      : Duy trì {alloc} cổ phiếu. Ưu tiên mã đang dẫn dắt (Leader)."
                            txt += f"\n     - 🛒 Vùng Mua Gia Tăng   : Nhặt thêm hàng khi Index test lại hỗ trợ {s1_val}. Mạnh dạn gom nếu về {s2_val}."
                            txt += f"\n     - 🎯 Vùng Chốt Một Phần  : Tỉa lộc khi Index chạm cản {r1_val} - {r2_val}. Không bán sạch khi trend còn sống."
                            txt += f"\n     - ✂ Báo Động Đỏ Khi Nào? : Nếu Index đóng cửa thủng hỗ trợ {s1_val} kèm Volume lớn -> Hạ về 50% tiền mặt ngay."
                        
                        elif reg == "UPTREND_UNDER_PRESSURE":
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - CÓ FTD NHƯNG ÁP LỰC BÁN ĐANG TĂNG ({dist_count} phiên phân phối)."
                            txt += f"\n     - ⚠️ HÀNH ĐỘNG NGAY      : BÁN BỚT HÀNG YẾU NGAY HÔM NAY. Không chờ hồi lên cản mới bán!"
                            txt += f"\n     - Cơ Cấu Danh Mục        : Loại bỏ ngay các mã gãy MA20 / mã thua lỗ nhiều. Chỉ giữ {alloc} cổ phiếu Leader khỏe."
                            txt += f"\n     - 🛡️ Kịch Bản Xấu Nhất   : Nếu Index thủng {s1_val} -> GIỮ TIỀN MẶT 70%+. Hàng yếu sẽ rớt gấp 2-3 lần Index."
                            txt += f"\n     - 🛒 Mua Mới Được Không?  : CẤM FOMO. Chỉ test lượng nhỏ nếu Index đạp chuẩn về sâu {s2_val} rồi nảy lên giữ được."
                            txt += f"\n     - 📌 FTD Còn Sống Không?  : FTD ({ftd_quality}) sẽ BỊ HỦY nếu Index đóng cửa dưới mốc FTD cũ. Lúc đó -> chuyển sang DOWNTREND."
                        
                        elif reg == "RECOVERY":
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - FTD VỪA KÍCH HOẠT, MỚI VƯỢT MA10. CÒN SỚM ĐỂ BẮT ĐÁY MẠNH."
                            txt += f"\n     - Phân Bổ Tỷ Trọng      : Giữ {alloc} cổ phiếu. Test hàng nhỏ ở mã Leader."
                            txt += f"\n     - 🛒 Mua Ở Đâu?          : Chỉ nhặt khi Index duy trì trên {s1_val}. Nếu xé rào vượt {r1_val} kèm vol -> tăng lên 50%."
                            txt += f"\n     - ✂ Stoploss Cho Cả Port : Rút về 10% cổ phiếu nếu Index quay đầu thủng {sl_idx}."
                        
                        else:  # WEAK_RECOVERY hoac cac trang thai FTD khac
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - FTD CÓ NHƯNG XUNG LỰC CHƯA RÕ. MÔI TRƯỜNG TRUNG TÍNH."
                            txt += f"\n     - Mua Dò Đường           : Giải ngân {alloc} test vị thế nhỏ khi Index nén quanh {s1_val}."
                            txt += f"\n     - Chờ Xác Nhận           : Chỉ tăng tỷ trọng lên 50%+ khi Index vượt {r1_val} kèm thanh khoản rõ ràng."
                            txt += f"\n     - ✂ Rút Lui Nếu          : Index đóng cửa dưới {sl_idx} -> xoá vị thế test, giữ tiền mặt chờ."
                    else:
                        if ra_day > 0:
                            txt += f"\n  👉 THỊ TRƯỜNG [ĐANG NỖ LỰC HỒI PHỤC - RA Ngày {ra_day}] - CHỜ XÁC NHẬN FTD."
                            txt += f"\n     - Tình Trạng             : Thị trường đang cố ngưng rơi nhưng CHƯA CÓ FTD. Mọi nhịp hồi đều có thể là bẫy."
                            txt += f"\n     - Tỷ Trọng Khuyên        : Giữ {alloc} cổ phiếu (toàn mã cực khỏe)."
                            txt += f"\n     - 🛒 Canh Mua Test        : Mua mồi 10% ở mã Leader nền đẹp khi Index đang test hỗ trợ {s1_val}."
                            txt += f"\n     - ⚡ Khi Nào Tăng Tỷ Trọng: Chờ FTD xuất hiện (Volume bùng nổ > TB20 + Close tăng > 1.5%). Khi đó mới nâng lên 40%."
                            txt += f"\n     - ✂ Đổ Máu Khi Nào?      : Nếu Index thủng đáy cũ {s2_val} -> BÁN SẠCH, RA NGOÀI HOÀN TOÀN."
                        elif reg == "MARKET_WEAKENING":
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - ĐÀ TĂNG CHẤM DỨT, BẮT ĐẦU SUY YẾU."
                            txt += f"\n     - ⚠️ HÀNH ĐỘNG NGAY      : Cắt bỏ mã yếu NGAY LẬP TỨC. Không đợi hồi, không gồng."
                            txt += f"\n     - Tỷ Trọng Phòng Thủ     : Tối đa {alloc} cổ phiếu. Chỉ giữ mã còn trên MA50."
                            txt += f"\n     - 🔪 Người Kẹp Hàng Nặng : Canh bất kỳ nhịp kéo ảo nào chạm gần {r1_val} -> BÁN XẢ giảm tải. Đừng hy vọng."
                            txt += f"\n     - 🛒 Mua Lại Khi Nào?    : Chỉ khi Index đạp rã thật sâu về tận {s2_val} + xuất hiện FTD mới."
                        elif reg == "SIDEWAY":
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - ĐI NGANG BIÊN HẸP, KHÔNG CÓ XU HƯỚNG RÕ."
                            txt += f"\n     - Chiến Lược             : SWING TRADE biên. Mua sát {s1_val}, bán sát {r1_val}."
                            txt += f"\n     - Tỷ Trọng               : {alloc} cổ phiếu, ưu tiên mã có câu chuyện riêng."
                            txt += f"\n     - ✂ Rào Chắn             : Thủng {s2_val} -> chuyển sang phòng thủ 100% tiền mặt."
                        else:  # DOWNTREND / UNKNOWN
                            txt += f"\n  👉 THỊ TRƯỜNG [{reg}] - DOWNTREND / RỦI RO LỚN. ƯU TIÊN ÔM TIỀN MẶT."
                            txt += f"\n     - ⛔ LỆNH CẤM             : TUYỆT ĐỐI KHÔNG BẮT ĐÁY. Mọi nhịp hồi đều là bẫy Bull Trap."
                            txt += f"\n     - ✂ Cắt Lỗ Kỷ Luật       : Bán tháo toàn bộ mã yếu, mã thua lỗ. Không ngoại lệ."
                            txt += f"\n     - 🔪 Canh Xả Hàng Kẹp    : Nếu có nhịp Bull Trap nảy lên sát {r1_val} -> thoát sạch. Đây là CƠ HỘI VÀNG để chạy."
                            txt += f"\n     - 🛒 Vùng Cứu Trợ        : Chỉ quay lại thị trường khi Index đạp cạn kiệt về tận {s2_val} + FTD mới xác nhận."
                        
                    # Dong tong ket tu State Engine
                    if st:
                        txt += f"\n\n  📊 ĐÁNH GIÁ TỔNG HỢP TỪ ROBOT:"
                        txt += f"\n     Xu hướng: {st_pri} | Hành vi: {st_sec} | Tín hiệu: {st_sig}"
                        txt += f"\n     Xác suất tiếp diễn xu hướng hiện tại: {st_win}"
                        txt += f"\n     ➡️ TỶ TRỌNG KHUYẾN NGHỊ: NẮM GIỮ {alloc} CỔ PHIẾU."
                        if st_avoid:
                            txt += f"\n     ⛔ BỘ LỌC RỦI RO: ĐANG BẬT - TUYỆT ĐỐI KHÔNG MUA MỚI."
                    
                    return txt





                vn_key = next((k for k in self.data_dict.keys() if "VNINDEX" in k), "VNINDEX")


                hn_key = next((k for k in self.data_dict.keys() if "HNX" in k or "HAINDEX" in k), "HNXINDEX")


                


                vn_full = analyze_full_index(self.data_dict.get(vn_key))


                hn_full = analyze_full_index(self.data_dict.get(hn_key))


                


                report = []
                report.append("\n" + "="*60)
                report.append(f"💎 ĐÁNH GIÁ TỔNG QUAN THỊ TRƯỜNG - {vn_full['date']} - AIC code! 💎")
                report.append(f"A. ĐỘ RỘNG THỊ TRƯỜNG (BREADTH): {breadth_res['breadth_label']}")
                report.append(f" - Tổng mã quét: {breadth_res['total_scanned']}")
                report.append(f" - Tỷ lệ mã > MA20: {breadth_res.get('strong_stocks_ma20_pct', 'N/A')}%")
                report.append(f" - Tỷ lệ mã > MA50: {breadth_res['strong_stocks_pct']}%")
                
                report.append("\n" + "="*60)
                report.append(format_index(vn_key, vn_full, prefix="B. "))
                if hn_full:
                    report.append("\n" + "="*60)
                    report.append(format_index(hn_key, hn_full, prefix="C. "))

                report.append("\n" + "="*60)


                    


                report.append("\n" + "="*60)


                


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
                # df_vn has sequential numerical index and a 'Date' column. df_plot has Date string index.
                df_vn_indexed = df_vn.copy()
                df_vn_indexed['DateStr'] = pd.to_datetime(df_vn_indexed['Date']).dt.strftime('%Y-%m-%d')
                df_vn_indexed = df_vn_indexed.set_index('DateStr')
                
                df_plot_dates = pd.to_datetime(df_plot.index).strftime('%Y-%m-%d')
                common_dates = df_plot_dates.intersection(df_vn_indexed.index)
                
                df_vn_plot = df_vn_indexed.loc[common_dates]
                if not df_vn_plot.empty:
                    ax2 = ax1.twinx()
                    
                    up = df_vn_plot[df_vn_plot['Close'] >= df_vn_plot['Open']]
                    down = df_vn_plot[df_vn_plot['Close'] < df_vn_plot['Open']]
                    
                    # Candlestick Bodies
                    ax2.bar(mdates.date2num(pd.to_datetime(up.index)), up['Close'] - up['Open'], bottom=up['Open'], color='white', edgecolor='#455A64', linewidth=1.2, width=0.6, alpha=0.9, zorder=3)
                    ax2.bar(mdates.date2num(pd.to_datetime(down.index)), down['Open'] - down['Close'], bottom=down['Close'], color='#455A64', edgecolor='#455A64', width=0.6, alpha=0.9, zorder=3)
                    
                    # Candlestick Wicks
                    ax2.vlines(mdates.date2num(pd.to_datetime(up.index)), up['Low'], up['High'], color='#455A64', linewidth=1.2, zorder=2)
                    ax2.vlines(mdates.date2num(pd.to_datetime(down.index)), down['Low'], down['High'], color='#455A64', linewidth=1.2, zorder=2)
                    
                    # Dummy line for legend
                    import matplotlib.lines as mlines
                    line3 = mlines.Line2D([], [], color='#455A64', marker='s', linestyle='None', markersize=8, label='VNINDEX (Candles)')
                    
                    ax2.set_ylabel('Điểm số VNINDEX', color='#455A64', fontsize=10, fontweight='bold')
                    ax2.tick_params(axis='y', labelcolor='#455A64')
                    ax2.grid(False) # avoid overlapping grid
                    
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


