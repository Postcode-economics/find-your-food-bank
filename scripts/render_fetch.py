"""Headless Chromium fetch for pages that draw their content with JavaScript (new Trussell food bank sites list the
centre cards only after scripts run; Dean, 23 Oct 23:36). Same return shape as trussell_times.fetch: (http, final_url, html).
Playwright's sync API may only be used from the thread that started it. times_finder reads sites from 12 threads,
which broke every render in GitHub Actions on 23 Oct ('greenlet.error: cannot switch to a different thread').
So dedicated browser threads own Playwright (each its own instance) and every caller queues its URL to them (thread-safe).
24 Oct: with one worker, 12 callers queued faster than it could render and every caller's 120s wait ran out (http 0 on 41
of 45 sites in Actions). Now WORKERS threads, and a caller waits for its own job instead of timing out and re-queuing."""
import atexit, os, queue, threading
_q = queue.Queue(); _ts = []; WORKERS = int(os.environ.get("RENDER_WORKERS", "4")); _lock = threading.Lock()
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 foodbank-map-refresh"
def _worker():
    from playwright.sync_api import sync_playwright
    exe = os.environ.get("CHROME_PATH")
    with sync_playwright() as pw:
        try: br = pw.chromium.launch(args=["--no-sandbox"], **({"executable_path": exe} if exe else {}))
        except Exception as e:   # a browser that will not start must answer every job (http 0), never leave callers hanging
            print("render_fetch: browser launch failed:", type(e).__name__, str(e)[:160], flush=True)
            while True:
                job = _q.get()
                if job is None: return
                job[2].append((0, job[0], "")); job[3].set()
        while True:
            job = _q.get()
            if job is None: break
            url, wait_ms, box, done = job
            try:
                pg = br.new_page(user_agent=UA)
                r = pg.goto(url, wait_until="domcontentloaded", timeout=30000)
                try: pg.wait_for_selector("text=/Collection times|Opening times|Get directions/i", timeout=wait_ms * 3)
                except Exception: pg.wait_for_timeout(wait_ms)
                box.append((r.status if r else 0, pg.url, pg.content())); pg.close()
            except Exception as e:
                box.append((0, url, "")); print("render_fetch:", url, type(e).__name__, str(e)[:120], flush=True)
            finally: done.set()
        br.close()
def _start():
    with _lock:
        if not _ts: atexit.register(close)
        _ts[:] = [t for t in _ts if t.is_alive()]
        while len(_ts) < WORKERS:
            t = threading.Thread(target=_worker, daemon=True, name="render-fetch-%d" % len(_ts)); t.start(); _ts.append(t)
def close():
    for t in _ts: _q.put(None)
    for t in _ts: t.join(timeout=20)
def fetch(url, tries=2, wait_ms=4000):
    _start(); box = []
    for _ in range(tries):
        box, done = [], threading.Event(); _q.put((url, wait_ms, box, done))
        done.wait(1800)   # wait for our own job; never re-queue a job that is still waiting in line
        if box and box[0][0] == 200 and box[0][2]: return box[0]
    return box[0] if box else (0, url, "")
