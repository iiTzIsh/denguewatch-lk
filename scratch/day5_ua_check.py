"""Day 5 debug: does the WER page answer differently depending on the User-Agent?"""
import requests

URL = "https://www.epid.gov.lk/weekly-epidemiological-report"
AGENTS = {
    "our custom UA": "DengueWatchLK/0.1 (student portfolio project)",
    "requests default": requests.utils.default_user_agent(),
    "browser-like + project": "Mozilla/5.0 (compatible; DengueWatchLK/0.1; student portfolio project)",
    "full browser": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
}

for name, ua in AGENTS.items():
    try:
        r = requests.get(URL, headers={"User-Agent": ua}, timeout=30)
        print(f"{name:25} -> {r.status_code}  ({len(r.text)} chars, {r.text.lower().count('.pdf')} '.pdf' mentions)")
    except requests.RequestException as exc:
        print(f"{name:25} -> ERROR {exc}")
