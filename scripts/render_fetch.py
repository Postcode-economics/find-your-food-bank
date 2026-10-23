"""Headless Chromium fetch for pages that draw their content with JavaScript (new Trussell food bank sites list the
centre cards only after scripts run; Dean, 23 Oct 23:36). Same return shape as trussell_times.fetch: (http, final_url, html).
Used by times_finder --render (GitHub Actions installs Playwright + Chromium for that step)."""
import atexit
_pw = _br = None
def _browser():
    global _pw, _br
    if _br is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        import os; exe = os.environ.get("CHROME_PATH")
        _br = _pw.chromium.launch(args=["--no-sandbox"], **({"executable_path": exe} if exe else {}))
        atexit.register(close)
    return _br
def close():
    global _pw, _br
    try:
        if _br: _br.close()
        if _pw: _pw.stop()
    except Exception: pass
    _pw = _br = None
def fetch(url, tries=2, wait_ms=4000):
    for _ in range(tries):
        try:
            pg = _browser().new_page(user_agent="Mozilla/5.0 (foodbank-map refresh; headless render)")
            r = pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            try: pg.wait_for_selector("text=/Collection times|Opening times|Get directions/i", timeout=wait_ms * 3)
            except Exception: pg.wait_for_timeout(wait_ms)
            out = (r.status if r else 0, pg.url, pg.content()); pg.close(); return out
        except Exception: continue
    return 0, url, ""
