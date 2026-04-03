import json
import os
import re
from pathlib import Path

class ConfigManager:
    def __init__(self, config_path="config.json"):
        self.config_path = Path(config_path)
        self.default_config = {
            "vietstock_api_url": "https://finance.vietstock.vn/data/KQGDThongKeGiaPaging",
            "vietstock_index_url": "https://finance.vietstock.vn/data/KQGDThongKeGiaStockPaging",
            "stocklist_api_url": "https://finance.vietstock.vn/data/stocklist",
            "bypass_pageSize": 50,
            "cookies": {},
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
                "Connection": "keep-alive"
            }
        }
        self.config = self._load()

    def _load(self):
        if not self.config_path.exists():
            self._save(self.default_config)
            return self.default_config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Merge with defaults to ensure all keys exist
                for k, v in self.default_config.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            return self.default_config

    def _save(self, data):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def get(self, key):
        return self.config.get(key, self.default_config.get(key))

    def set(self, key, value):
        self.config[key] = value
        self._save(self.config)

    def update_url(self, url):
        self.set("vietstock_api_url", url)

    def _sanitize_curl(self, text):
        """Remove Windows shell escapes (^) and normalize quoting for parsing."""
        if not text: return ""
        # 1. Remove ^ line continuations and shell escapes
        text = text.replace(" ^\n", " ").replace("^\n", " ").replace("^$", "$").replace("^\"", "\"")
        # 2. Handle double-escaped quotes like ^\^" or \^"
        text = text.replace("^\\^\"", "\"").replace("\\^\"", "\"").replace("\\\"", "\"")
        # 3. Last resort: remove any remaining ^ before symbols that don't need escaping in Python
        text = re.sub(r"\^([=:\s\$])", r"\1", text)
        return text

    def _is_tracked_header(self, name):
        tracked = {
            "user-agent", "referer", "origin", "accept-language", "accept",
            "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site",
            "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
            "x-requested-with", "content-type"
        }
        return name.lower() in tracked

    def parse_input(self, text):
        """
        Extract cookies, tokens and headers from raw text (cURL or Browser Headers).
        Always returns True if anything was updated.
        """
        if not text: return False
        
        # Cleanup input (remove helper markers if present)
        text = re.sub(r'---.*---', '', text).strip()
        
        # 1. Handle Multi-cURL paste: Pick the right one
        target_text = text
        if "curl" in text.lower():
            # Split by 'curl ' but handle the first one
            chunks = re.split(r'curl\s+', text, flags=re.IGNORECASE)
            chunks = [c.strip() for c in chunks if c.strip()]
            
            # Prioritize Vietstock Data Paging or StockList
            priority_keywords = ["KQGDThongKeGiaPaging", "GetTemplateByName", "stocklist", "finance.vietstock.vn"]
            
            best_chunk = ""
            for kw in priority_keywords:
                for c in chunks:
                    if kw in c:
                        best_chunk = c
                        break
                if best_chunk: break
            
            target_text = "curl " + (best_chunk or chunks[0])

        # Detect if we are processing a cURL command
        is_curl = "curl" in target_text.lower()[:50]
        if is_curl:
            target_text = self._sanitize_curl(target_text)
        
        updates = {
            "cookies": {},
            "headers": {}, # Clean slate for headers to avoid duplicates
            "payload_token": "",
            "bypass_pageSize": None
        }
        
        # Initialize headers with existing ones from config, but normalized
        old_headers = self.config.get("headers", {})
        for k, v in old_headers.items():
            updates["headers"][k] = v

        # 2. Extract Headers (Cookie, User-Agent, Origin, etc.)
        if is_curl:
            # Handle both single and double quotes for headers, with potential internal quotes
            raw_headers = re.findall(r"(?:-H|--header)\s+(?:'([^']+)'|\"((?:\\\\\"|[^\"])+)\")", target_text, re.IGNORECASE)
            
            for h_tuple in raw_headers:
                h = h_tuple[0] or h_tuple[1]
                if h and ":" in h:
                    k, v = h.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k.lower() == "cookie":
                        updates["cookies"].update(self._parse_cookie_str(v))
                    elif self._is_tracked_header(k):
                        # Normalize key name: convert to Title-Case (e.g. user-agent -> User-Agent)
                        # but keep sec-ch-ua as is or Title-Case correctly
                        norm_k = "-".join([p.capitalize() for p in k.split("-")])
                        updates["headers"][norm_k] = v
            
            # Data raw for token - handle common variations
            data_match = re.search(r"--data(?:-raw|-binary|-ascii)?\s+(?:'([^']+)'|\"((?:\\\\\"|[^\"])+)\")", target_text, re.IGNORECASE)
            if data_match:
                data_val = data_match.group(1) or data_match.group(2)
                params = data_val.split("&")
                for p in params:
                    if "=" in p:
                        tk_key, tv_val = p.split("=", 1)
                        if tk_key == "__RequestVerificationToken":
                            updates["payload_token"] = tv_val
                        elif tk_key.lower() == "pagesize":
                            try:
                                updates["bypass_pageSize"] = int(tv_val)
                            except Exception:
                                pass
        else:
            # Format 2: Raw Browser Headers or URL
            is_url = target_text.startswith("http")
            
            lines = [l.strip() for l in target_text.split("\n") if l.strip()]
            for line in lines:
                # If it's a URL, extract token from query
                if line.startswith("http"):
                    token_match = re.search(r"__RequestVerificationToken[=:\s]+([A-Za-z0-9._-]{40,})", line)
                    if token_match:
                        updates["payload_token"] = token_match.group(1).split("&")[0].strip(";")
                    
                    # Also look for pageSize in URL
                    page_match = re.search(r"[?&]pageSize=(\d+)", line, re.IGNORECASE)
                    if page_match:
                        updates["bypass_pageSize"] = int(page_match.group(1))
                    continue

                # Handle raw header lines "Key: Value" or "Key [tab] Value"
                if ":" in line:
                    k, v = line.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k.lower() == "cookie":
                        updates["cookies"].update(self._parse_cookie_str(v))
                    elif self._is_tracked_header(k):
                        norm_k = "-".join([p.capitalize() for p in k.split("-")])
                        updates["headers"][norm_k] = v

        # Final check for token using direct regex if line-by-line failed
        if not updates["payload_token"]:
            # 1. Try to find it in the cookies we just parsed
            if "__RequestVerificationToken" in updates["cookies"]:
                updates["payload_token"] = updates["cookies"]["__RequestVerificationToken"]
            
            # 2. Try regex again on the target text
            if not updates["payload_token"]:
                token_match = re.search(r"__RequestVerificationToken[=:\s]+([A-Za-z0-9._-]{50,})", target_text)
                if token_match:
                    updates["payload_token"] = token_match.group(1).strip(";").strip()
                else:
                    # Look for any very long token-like string (last resort)
                    long_strings = re.findall(r"([A-Za-z0-9._-]{100,})", target_text)
                    for s in long_strings:
                        if len(s) > 100 and "http" not in s and "/" not in s:
                            updates["payload_token"] = s
                            break

        # Commit
        updated = False
        
        # LOGIC: If we found a token but NO cookies, the cookies in the clipboard were missing (pasted URL).
        # We must CLEAR old cookies to prevent "mismatched" sessions (Old Cookie + New Token = 200 limit).
        if updates["payload_token"] and not updates["cookies"]:
             # If it was a cURL/Header paste, we expect cookies. If not, it's a URL.
             # We clear to be safe.
             self.set("cookies", {}) # Clear old cookies
             updated = True

        if updates["cookies"]:
            self.set("cookies", updates["cookies"])
            updated = True
            
        if updates["payload_token"]:
            self.set("payload_token", updates["payload_token"])
            updated = True
            
        if updates["bypass_pageSize"] is not None:
             self.set("bypass_pageSize", updates["bypass_pageSize"])
             updated = True

        
        if updates["headers"]:
             current_headers = self.config.get("headers", {})
             current_headers.update(updates["headers"])
             # Normalize keys to lowercase for comparison, but keep original casing for the dict
             normalized_headers = {k.lower(): k for k in current_headers.keys()}
             for k, v in updates["headers"].items():
                 key_lower = k.lower()
                 if key_lower in normalized_headers:
                     current_headers[normalized_headers[key_lower]] = v
                 else:
                     current_headers[k] = v
             self.set("headers", current_headers)
             updated = True
             
        return updated

    def _is_tracked_header(self, k):
        """Check if header key is one we want to keep for simulation."""
        tracked = ["user-agent", "origin", "referer", "x-requested-with", 
                   "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
                   "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site", "accept-language"]
        return k.lower() in tracked

    def _extract_header_field(self, k, v, updates):
        k_lower = k.lower()
        if k_lower == "cookie":
            updates["cookies"].update(self._parse_cookie_str(v))
        elif self._is_tracked_header(k):
            updates["headers"][k] = v

    def _parse_cookie_str(self, cookie_str):
        cookies = {}
        pairs = cookie_str.split(";")
        for p in pairs:
            if "=" in p:
                k, v = p.strip().split("=", 1)
                cookies[k] = v
        return cookies
