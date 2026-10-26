"""Dean's standing rule (25 Oct 2026, asked 3 times): helpmap.uk opens DARK by default, whatever the OS/phone light setting.
Only the visitor's own saved 'Light mode' choice (localStorage light=1) overrides it; storage failing (Instagram webview) = dark.
Usage: python scripts/dark_default.py [BASE_URL] [--webkit]. Checks Chromium (and WebKit if asked / available). Exit 1 on failure."""
import sys
from playwright.sync_api import sync_playwright
IG = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 330.0.0.0 helpmap-check'
BLOCK = "for(const k of ['localStorage','sessionStorage'])Object.defineProperty(window,k,{get(){throw new DOMException('denied','SecurityError')}});"
def run(base, engines):
    bad = []
    with sync_playwright() as p:
        for eng in engines:
            try: b = getattr(p, eng).launch(**({'executable_path': '/usr/bin/google-chrome'} if eng == 'chromium' and __import__('os').path.exists('/usr/bin/google-chrome') else {}))
            except Exception as e: bad.append((eng, 'cannot launch: %s' % str(e)[:80])); continue
            for scheme in ('light', 'no-preference', 'dark'):
                for case in ('fresh', 'blocked', 'saved-light', 'saved-dark'):
                    c = b.new_context(color_scheme=scheme, viewport={'width': 390, 'height': 844}, user_agent=IG if case == 'blocked' else None)
                    if case == 'blocked': c.add_init_script(BLOCK)
                    if case.startswith('saved'): c.add_init_script("try{if(!sessionStorage.getItem('dd')){sessionStorage.setItem('dd','1');localStorage.setItem('light','%s')}}catch(e){}" % ('1' if case == 'saved-light' else '0'))
                    pg = c.new_page()
                    try:
                        pg.goto(base + '/?nocount', wait_until='load', timeout=45000); pg.wait_for_timeout(2500)
                        light = pg.evaluate("document.documentElement.classList.contains('light')")
                        bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
                    except Exception as e: light, bg = None, 'error %s' % str(e)[:60]
                    want = case == 'saved-light'
                    ok = light is want
                    print('PASS' if ok else 'FAIL', eng, scheme, case, 'light' if light else 'dark', bg, flush=True)
                    if not ok: bad.append((eng, scheme, case, light, bg))
                    c.close()
            b.close()
    return bad
if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    base = (a[0] if a else 'https://helpmap.uk').rstrip('/')
    bad = run(base, ['chromium'] + (['webkit'] if '--webkit' in sys.argv else []))
    print('dark default: %d problem(s)' % len(bad)); sys.exit(1 if bad else 0)
