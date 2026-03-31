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

    def parse_input(self, text):
        """
        Extract cookies, tokens and headers from raw text (cURL or Browser Headers).
        Always returns True if anything was updated.
        """
        if not text: return False
        
        updates = {
            "cookies": {},
            "headers": self.config.get("headers", {}).copy(),
            "payload_token": ""
        }
        
        # Cleanup input (remove helper markers if present)
        text = re.sub(r'---.*---', '', text).strip()
        
        # 1. Detect format
        is_curl = "curl" in text.lower()[:20]
        
        # 2. Extract Headers (Cookie, User-Agent, Origin, etc.)
        if is_curl:
            headers = re.findall(r"(?:-H|--header)\s+['\"]([^'\"]+)['\"]", text, re.IGNORECASE)
            for h in headers:
                if ":" in h:
                    k, v = h.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k.lower() == "cookie":
                        updates["cookies"] = self._parse_cookie_str(v)
                    elif k.lower() in ["user-agent", "origin", "referer", "x-requested-with"]:
                        updates["headers"][k] = v
            
            # Data raw for token
            data_match = re.search(r"--data(?:-raw|-binary)?\s+['\"]([^'\"]+)['\"]", text, re.IGNORECASE)
            if data_match:
                params = data_match.group(1).split("&")
                for p in params:
                    if "=" in p:
                        tk_key, tv_val = p.split("=", 1)
                        if tk_key == "__RequestVerificationToken":
                            updates["payload_token"] = tv_val
        else:
            # Check if it's a URL with parameters
            is_url = text.startswith("http")
            if is_url:
                # Use a more permissive regex for tokens in URLs
                token_match = re.search(r"__RequestVerificationToken[=:\s]+([A-Za-z0-9._-]{40,})", text)
                if token_match:
                    updates["payload_token"] = token_match.group(1)
                
                sid_match = re.search(r"ASP.NET_SessionId=([A-Za-z0-9]+)", text)
                if sid_match:
                    updates["cookies"]["ASP.NET_SessionId"] = sid_match.group(1)

            # Raw Headers or Payload (Skip if it's just a single-line URL that we already parsed)
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if not is_url or len(lines) > 1:
                for line in lines:
                    # Skip lines that are just URLs to avoid junk extraction
                    if line.startswith("http"): continue

                    # Catch verification token anywhere in the line
                    if "__RequestVerificationToken" in line:
                        # Try to find a long string after the key
                        parts = re.split(r"[:\s=]+", line)
                        for p in parts:
                            if len(p) > 40 and p != "__RequestVerificationToken":
                                updates["payload_token"] = p
                                break

                    if ":" in line:
                        k, v = line.split(":", 1)
                        k, v = k.strip(), v.strip()
                        self._extract_header_field(k, v, updates)

        # Final check for token using direct regex if line-by-line failed
        if not updates["payload_token"]:
            # Vietstock tokens can be very long and vary in length
            token_match = re.search(r"__RequestVerificationToken[=:\s]+([A-Za-z0-9._-]{50,})", text)
            if token_match:
                updates["payload_token"] = token_match.group(1)
            else:
                # Last resort: find any string > 100 chars (likely token)
                long_strings = re.findall(r"([A-Za-z0-9._-]{100,})", text)
                for s in long_strings:
                    # Exclude things that are clearly not tokens (like URLs or long paths)
                    if len(s) > 100 and "http" not in s and "/" not in s:
                        updates["payload_token"] = s
                        break

        # Commit
        updated = False
        if updates["cookies"]:
            self.set("cookies", updates["cookies"])
            updated = True
        if updates["payload_token"]:
            self.set("payload_token", updates["payload_token"])
            updated = True
        
        if updates["headers"]:
             current_headers = self.config.get("headers", {})
             current_headers.update(updates["headers"])
             self.set("headers", current_headers)
             updated = True
             
        return updated

    def _extract_header_field(self, k, v, updates):
        if k.lower() == "cookie":
            updates["cookies"] = self._parse_cookie_str(v)
        elif k.lower() in ["user-agent", "origin", "referer", "x-requested-with"]:
            updates["headers"][k] = v

    def _parse_cookie_str(self, cookie_str):
        cookies = {}
        pairs = cookie_str.split(";")
        for p in pairs:
            if "=" in p:
                k, v = p.strip().split("=", 1)
                cookies[k] = v
        return cookies
