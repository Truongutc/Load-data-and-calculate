from tinvest.config_manager import ConfigManager

# Raw copy of headers from chat
raw_headers = """
Cookie:
language=vi-VN; Theme=Light; AnonymousNotification=; isShowLogin=true; packName=Basic; qPerDay=0; qPerMonth=0; vst_isShowTourGuid=true; ASP.NET_SessionId=a1trpmeyehax5tl4ghkatq5x; __RequestVerificationToken=DPnNsyhukVoDKfP11RHiGF89VoF-MbcTwgq6b1masrH_hcTXUBez2VEv5pSv29DwORy4Z_4ZbwslUKhMQtn5iI332-k5fLh9I69XVWlCCb81; _gid=GA1.2.1631650041.1774845802; _gat_UA-1460625-2=1; CookieLogin=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9uYW1lIjoiaHV1dHJ1b25ndXRjQGdtYWlsLmNvbSIsImh0dHA6Ly9zY2hlbWFzLnhtbHNvYXAub3JnL3dzLzIwMDUvMDUvaWRlbnRpdHkvY2xhaW1zL2hhc2giOiJzay1oNHp5T0NoVTJScHBVeUVYNHJhSGlnIiwiaHR0cDovL3NjaGVtYXMueG1sc29hcC5vcmcvd3MvMjAwNS8wNS9pZGVudGl0eS9jbGFpbXMvbmFtZWlkZW50aWZpZXIiOiJodXV0cnVvbmd1dGNAZ21haWwuY29tIiwiZXhwIjoxNzc3NDM3ODIxLCJpc3MiOiIudmlldHN0b2NrLnZuIiwiYXVkIjoiLnZpZXRzdG9jay52biJ9.uolVu_gcdeqfhWMORXetOb7yOvMQalKF5VM07kBA5uI; vst_usr_lg_token=cGbKu/0lM0uf5AUYyPkpGQ==; _ga_EXMM0DKVEX=GS2.1.s1774845797$o135$g1$t1774845818$j39$l0$h0; _ga=GA1.2.1417740156.1752282620
User-Agent:
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36
__RequestVerificationToken: XKyeV5m694TedtPh8g_hK2sHUxKREzB5VjauQv3ZXgDkgpwyDv0AKVpCcAFvP5wkDALKfuo_IelGHt_sm6m_yHGXtnlYChAOikAD73GWl7Lw4PY2mCHznW0AmFLWcCoL3mIWqbGFFe__ytjllzysBw2
"""

cm = ConfigManager()
success = cm.parse_input(raw_headers)

if success:
    print("✅ Successfully ingested browser headers and tokens into config.json")
    print("Cookies found:", len(cm.get("cookies")))
    print("Payload Token applied:", cm.get("payload_token")[:20] + "...")
else:
    print("❌ Failed to parse headers. Check format.")
