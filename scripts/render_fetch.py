"""Headless Chromium fetch for pages that draw their content with JavaScript (new Trussell food bank sites list the
centre cards only after scripts run; Dean, 23 Oct 23:36). Same return shape as trussell_times.fetch: (http, final_url, html).
Used by times_finder --render (GitHub Actions installs Playwright + Chromium for that step).

Playwright's sync API may only be used from the thread that started it ('greenlet.error: cannot switch to a different
thread', sweep run 40823719214, 29 Oct 2026: 68 renders lost). times_finder calls fetch from 12 worker threads, so
every render runs on one dedicated thread that owns the browser; callers wait for their own result."""
import atexit, queue, threading
_pw = _br = None
_jobs = queue.Queue()
_worker = None
_lock = threading.Lock()
def _browser():
    global _pw, _br
    if _br is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        import os; exe = os.environ.get("CHROME_PATH")
        _br = _pw.chromium.launch(args=["--no-sandbox"], **({"executable_path": exe} if exe else {}))
    return _br
def _close_browser():
    global _pw, _br
    try:
        if _br: _br.close()
        if _pw: _pw.stop()
    except Exception: pass
    _pw = _br = None
def _render(url, tries, wait_ms):
    for _ in range(tries):
        try:
            pg = _browser().new_page(user_agent="Mozilla/5.0 (foodbank-map refresh; headless render)")
            r = pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            try: pg.wait_for_selector("text=/Collection times|Opening times|Get directions/i", timeout=wait_ms * 3)
            except Exception: pg.wait_for_timeout(wait_ms)
            out = (r.status if r else 0, pg.url, pg.content()); pg.close(); return out
        except Exception: continue
    return 0, url, ""
def _loop():
    while True:
        job = _jobs.get()
        if job is None:
            _close_browser(); return
        args, box, done = job
        try: box.append(_render(*args))
        except BaseException: box.append((0, args[0], ""))
        finally: done.set()
def _start():
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_loop, name="render_fetch", daemon=True)
            _worker.start()
def close():
    global _worker
    with _lock:
        w, _worker = _worker, None
    if w is not None and w.is_alive():
        _jobs.put(None); w.join(timeout=60)
atexit.register(close)
def fetch(url, tries=2, wait_ms=4000):
    _start()
    box, done = [], threading.Event()
    _jobs.put(((url, tries, wait_ms), box, done))
    done.wait()
    return box[0] if box else (0, url, "")
