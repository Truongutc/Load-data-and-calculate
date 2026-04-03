import requests
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import time
import re
from tinvest.config_manager import ConfigManager

logger = logging.getLogger(__name__)

class VietstockClient:
    def __init__(self):
        self.config_mgr = ConfigManager()
        self.base_url = "https://finance.vietstock.vn"
        self.stats_api_url = self.config_mgr.get("vietstock_api_url")
        self.index_api_url = self.config_mgr.get("vietstock_index_url")
        self.stocklist_api_url = self.config_mgr.get("stocklist_api_url")
        
        self.session_limited = False # Track if current token is restricted to 200 items
        self.session = requests.Session()
        # Initialize headers from config
        self.session.headers.update(self.config_mgr.get("headers"))
        self.session.headers.update({
            "Referer": f"{self.base_url}/ket-qua-giao-dich?tab=thong-ke-gia",
            "Origin": self.config_mgr.get("headers").get("Origin", self.base_url)
        })
        
        # Inject Cookies
        cookies = self.config_mgr.get("cookies")
        if cookies:
            self.session.cookies.update(cookies)
        
        # Priority token from payload config
        self.manual_token = self.config_mgr.get("payload_token")
        self.token = None

    def refresh_from_config(self):
        """Update internal URLs and headers from config.json immediately."""
        self.config_mgr = ConfigManager() # Reload from disk
        self.stats_api_url = self.config_mgr.get("vietstock_api_url")
        self.index_api_url = self.config_mgr.get("vietstock_index_url")
        self.stocklist_api_url = self.config_mgr.get("stocklist_api_url")
        
        # Update session headers - Sync all tracked headers
        conf_headers = self.config_mgr.get("headers") or {}
        for k, v in conf_headers.items():
            if v and v.strip():
                self.session.headers[k] = v
        
        # Clear and Update session cookies
        self.session.cookies.clear()
        cookies = self.config_mgr.get("cookies")
        if cookies:
            self.session.cookies.update(cookies)
        else:
            # If no cookies, we must fetch a fresh session from the landing page
            logger.info("No cookies found in config. Fetching fresh session...")
            self.ensure_valid_session()
            
        # Update priority token
        self.manual_token = self.config_mgr.get("payload_token")
        self.session_limited = False # Reset status for new probe
        logger.info("Session refreshed from config with all headers.")

    def ensure_valid_session(self):
        """Visit landing page to get fresh ASP.NET_SessionId and __RequestVerificationToken cookies."""
        try:
            url = f"{self.base_url}/ket-qua-giao-dich?tab=thong-ke-gia"
            # We use a clean GET to the landing page to populate cookies
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                # Save captured cookies back to config manager for persistence
                current_cookies = requests.utils.dict_from_cookiejar(self.session.cookies)
                if current_cookies:
                    self.config_mgr.set("cookies", current_cookies)
                    logger.info(f"Automatically captured {len(current_cookies)} cookies.")
                return True
        except Exception as e:
            logger.error(f"Failed to ensure valid session: {e}")
        return False

    def check_session_status(self, date_str=None):
        """Perform a small probe to check if the session is currently limited."""
        if not date_str:
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            # Weekend handling
            if now.weekday() == 5: date_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            elif now.weekday() == 6: date_str = (now - timedelta(days=2)).strftime("%Y-%m-%d")
            
        try:
            # OPTIMIZED PROBE: Request exactly 201 items.
            # If server returns 200, it's limited. If 201, it's full.
            # This is 10x faster than requesting 2000 items.
            raw = self._fetch_page(1, date_str, page=1, page_size=201)
            if not raw or not isinstance(raw, list) or len(raw) < 3:
                return "ERROR"
            
            stocks = raw[2]
            if not stocks: return "NO_DATA"
            
            if len(stocks) == 200:
                self.session_limited = True
                
                # TEST BYPASS: Explicitly try to fetch records beyond 200
                bypass_size = self.config_mgr.get("bypass_pageSize") or 50
                if not bypass_size or bypass_size >= 200:
                    bypass_size = 50
                    
                test_page = max(2, (200 // bypass_size) + 1)
                test_raw = self._fetch_page(1, date_str, page=test_page, page_size=bypass_size)
                
                if test_raw and isinstance(test_raw, list) and len(test_raw) >= 3 and test_raw[2]:
                     return "LIMITED_BYPASSED" # Bypass works! We can get > 200 items.
                else:
                     return "LIMITED" # TRULY BLOCKED. Bypass failed to get more items.
            
            self.session_limited = False
            return "VALID"
        except Exception:
            return "ERROR"

    def get_token(self):
        """Fetch __RequestVerificationToken from Vietstock landing page."""
        try:
            url = f"{self.base_url}/ket-qua-giao-dich?tab=thong-ke-gia"
            response = self.session.get(url)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                token_input = soup.find('input', {'name': '__RequestVerificationToken'})
                if token_input:
                    self.token = token_input.get('value')
                    return self.token
        except Exception as e:
            logger.error(f"Error fetching Vietstock token: {e}")
        return None

    def get_stock_list(self, cat_id):
        """Fetch full symbol mapping for a category (1:HOSE, 2:HNX, 3:UPCOM)."""
        params = {"catID": cat_id}
        try:
            response = self.session.get(self.stocklist_api_url, params=params)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            logger.error(f"Error fetching stock list for cat {cat_id}: {e}")
        return []

    def _fetch_page(self, cat_id, date_str, page=1, page_size=2000):
        # Refresh config values
        self.refresh_from_config()
        
        token_to_use = self.manual_token if self.manual_token else self.token
        if not token_to_use:
             self.get_token()
             token_to_use = self.token
             
        payload = {
            "page": page,
            "pageSize": page_size,
            "catID": cat_id,
            "date": date_str,
            "__RequestVerificationToken": token_to_use
        }
        
        try:
            # Refresh URL in case user changed it in UI
            self.refresh_from_config()
            response = self.session.post(self.stats_api_url, data=payload)
            if response.status_code == 200:
                return json.loads(response.content.decode('utf-8-sig'))
        except Exception as e:
            logger.error(f"API Error fetching cat {cat_id} page {page}: {e}")
        return None

    def is_session_valid(self, raw_data, prev_records=None):
        """
        Validate if the session has real trading data.
        Rejects if all sampled stocks have zero volume or stagnant prices.
        """
        if not raw_data or not isinstance(raw_data, list) or len(raw_data) < 3:
            return False
        
        stocks = raw_data[2]
        if not stocks: return False
        
        # Check top 20 for signs of life
        samples = stocks[:20]
        total_vol = sum(int(s.get('M_TotalVol', 0)) for s in samples)
        if total_vol == 0: return False
        
        # Check if all OHLC are equal (market hasn't moved / invalid)
        stagnant = 0
        for s in samples:
            o = float(s.get('OpenPrice', 0))
            h = float(s.get('HighestPrice', 0))
            l = float(s.get('LowestPrice', 0))
            c = float(s.get('ClosePrice', 0))
            if o > 0 and o == h == l == c:
                stagnant += 1
        
        if stagnant == len(samples): return False
        return True

    def fetch_market_day(self, cat_id, date_str):
        """Fetch all stocks for a market category with automatic 200-limit bypass."""
        self.session.headers.update({
            "Referer": f"{self.base_url}/ket-qua-giao-dich?tab=thong-ke-gia&exchange={cat_id}"
        })
        
        all_data = []
        is_limited = False
        
        # 1. Try with large page size first
        raw_response = self._fetch_page(cat_id, date_str, page=1, page_size=2000)
        
        if not self.is_session_valid(raw_response):
            return [], False
            
        stocks_p1 = raw_response[2]
        
        # 2. Check for the 200 limit restriction
        if len(stocks_p1) == 200:
            logger.warning(f"Vietstock API truncated to 200 items. Triggering auto-bypass for Cat {cat_id}...")
            is_limited = True
            
            # BYPASS STRATEGY: Use dynamically calculated pageSize from user's URL or fallback to 50
            bypass_size = self.config_mgr.get("bypass_pageSize") or 50
            if not bypass_size or bypass_size >= 200: 
                bypass_size = 50 # Fallback safety
                
            logger.info(f"Using dynamic auto-bypass with pageSize={bypass_size}")
            
            all_data = []
            # We assume total items might be around 1000 for safety
            max_pages = max(20, (2000 // bypass_size) + 2)
            
            for p in range(1, max_pages):
                page_raw = self._fetch_page(cat_id, date_str, page=p, page_size=bypass_size)
                if page_raw and isinstance(page_raw, list) and len(page_raw) >= 3:
                    p_stocks = page_raw[2]
                    if not p_stocks: break # No more data
                    
                    # Merge unique tickers
                    existing_tickers = {s.get("StockCode") for s in all_data}
                    for s in p_stocks:
                        if s.get("StockCode") not in existing_tickers:
                            all_data.append(s)
                    
                    # If this small page returned fewer than requested, we are properly at the end
                    if len(p_stocks) < bypass_size: break
                else:
                    break
                time.sleep(0.3)
        else:
            # Not limited, use the 2000-mã response directly
            all_data.extend(stocks_p1)
            
            # Still check for legitimate paging (if total > 2000)
            total_pages = 1
            if len(raw_response) >= 4:
                tp_val = raw_response[3]
                if isinstance(tp_val, list) and len(tp_val) > 0:
                    total_pages = int(tp_val[0])
                elif isinstance(tp_val, (int, float)):
                    total_pages = int(tp_val)
            
            if total_pages > 1:
                for p in range(2, total_pages + 1):
                    page_raw = self._fetch_page(cat_id, date_str, page=p, page_size=2000)
                    if page_raw and isinstance(page_raw, list) and len(page_raw) >= 3:
                        all_data.extend(page_raw[2])
                    time.sleep(0.3) 
            
        return all_data, is_limited

    def fetch_index_day(self, ticker, cat_id, stock_id, date_str):
        """Fetch index data for a given date."""
        self.refresh_from_config()
        token_to_use = self.manual_token if self.manual_token else self.token
        if not token_to_use:
             self.get_token()
             token_to_use = self.token
             
        payload = {
            "page": 1,
            "pageSize": 20,
            "catID": cat_id,
            "stockID": stock_id,
            "fromDate": date_str,
            "toDate": date_str,
            "__RequestVerificationToken": token_to_use
        }
        
        try:
            response = self.session.post(self.index_api_url, data=payload)
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and len(data) >= 2:
                    records = data[1]
                    formatted = []
                    for r in records:
                        formatted.append({
                            "StockCode": ticker, # Use StockCode so format_to_df renames it correctly
                            "TradingDate": date_str,
                            "OpenPrice": r.get("OpenPrice", 0),
                            "HighestPrice": r.get("HighestPrice", 0),
                            "LowestPrice": r.get("LowestPrice", 0),
                            "ClosePrice": r.get("ClosePrice", 0),
                            "M_TotalVol": int(r.get("TotalVol", 0))
                        })
                    return formatted
        except Exception as e:
            logger.error(f"Error fetching index {ticker}: {e}")
        return []

    def get_missing_dates(self, last_date):
        """Return missing trading dates up to today."""
        now = datetime.now()
        effective_today = now.date()
        if now.weekday() == 5: effective_today -= timedelta(days=1)
        elif now.weekday() == 6: effective_today -= timedelta(days=2)
        
        if not last_date:
            last_date = now - timedelta(days=365)
        
        missing = []
        curr = (last_date + timedelta(days=1)).date()
        while curr <= effective_today:
            if curr.weekday() < 5:
                missing.append(curr.strftime("%Y-%m-%d"))
            curr += timedelta(days=1)
        return missing

    def format_to_df(self, raw_list):
        if not raw_list: return pd.DataFrame()
        
        df = pd.DataFrame(raw_list)
        if 'StockCode' in df.columns:
            df = df.rename(columns={
                'StockCode': 'Ticker',
                'TradingDate': 'Date',
                'OpenPrice': 'Open',
                'HighestPrice': 'High',
                'LowestPrice': 'Low',
                'ClosePrice': 'Close',
                'M_TotalVol': 'Volume'
            })
            # Convert prices to thousands ONLY for stocks. 
            # Indices like VNINDEX/HNX-INDEX are already in the correct unit.
            is_index = df['Ticker'].iloc[0] in ['VNINDEX', 'HNX-INDEX'] if not df.empty else False
            
            if not is_index:
                for col in ['Open', 'High', 'Low', 'Close']:
                    if col in df.columns:
                        df[col] = df[col] / 1000.0
            
            def parse_ms_date(d):
                if not isinstance(d, str): return d
                match = re.search(r'\((\d+)\)', d)
                if match:
                    ts = int(match.group(1)) / 1000.0
                    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                return d
            df['Date'] = df['Date'].apply(parse_ms_date)

        required = ['Ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        df = df[[c for c in required if c in df.columns]]
        return df
