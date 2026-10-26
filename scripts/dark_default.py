"""Dean's standing rule (25 Oct 2026, asked 3 times): helpmap.uk opens DARK by default, whatever the OS/phone light setting.
Only the visitor's own saved 'Light mode' choice (localStorage light=1) overrides it; storage failing (Instagram webview) = dark.

Playwright's default headless agent is answered with a "Just a moment..." page: no light class, and a
transparent background (black when the phone is set to dark). Saved light then looks like a failure and
the other cases look like passes. This uses the same browser identity and ready check as the journey
and old-links checks. A challenge page or an unstyled background is a failure.

Usage: python scripts/dark_default.py [BASE_URL] [--webkit]. Checks Chromium (and WebKit if asked / available). Exit 1 on failure."""
import os, re, sys
import check_browser as B
BLOCK = "for(const k of ['localStorage','sessionStorage'])Object.defineProperty(window,k,{get(){throw new DOMException('denied','SecurityError')}});"
NAVY = (10, 22, 40)    # --navy on html,body
WHITE = (255, 255, 255)  # html.light, html.light body
_RGB = re.compile(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)')
def parse_rgb(value):
    m = _RGB.search(value or '')
    return tuple(int(x) for x in m.groups()) if m else None
def ok_case(case, light, bg):
    """Saved light is the only light page, and the background is that theme, not the browser default."""
    want_light = case == 'saved-light'
    return light is want_light and parse_rgb(bg) == (WHITE if want_light else NAVY)
def run(base, engines):
    from playwright.sync_api import sync_playwright  # the plain pytest job has no Playwright; ok_case does not need it
    bad = []
    with sync_playwright() as p:
        for eng in engines:
            try:
                launch = {}
                if eng == 'chromium' and os.path.exists('/usr/bin/google-chrome'): launch['executable_path'] = '/usr/bin/google-chrome'
                b = getattr(p, eng).launch(**launch)
            except Exception as e: bad.append((eng, 'cannot launch: %s' % str(e)[:80])); continue
            for scheme in ('light', 'no-preference', 'dark'):
                for case in ('fresh', 'blocked', 'saved-light', 'saved-dark'):
                    c = B.new_context(b, color_scheme=scheme, viewport={'width': 390, 'height': 844}, instagram=(case == 'blocked'))
                    if case == 'blocked': c.add_init_script(BLOCK)
                    if case.startswith('saved'):
                        # Every document, including the one after a challenge page. A sessionStorage
                        # guard skipped the real page once an earlier document in the tab had set it.
                        c.add_init_script("try{localStorage.setItem('light','%s')}catch(e){}" % ('1' if case == 'saved-light' else '0'))
                    pg = c.new_page(); light, bg = None, ''
                    try:
                        B.goto(pg, base.rstrip('/') + '/?nocount')
                        light = pg.evaluate("document.documentElement.classList.contains('light')")
                        bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
                    except Exception as e: light, bg = None, 'error %s' % str(e)[:160]
                    ok = ok_case(case, light, bg)
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
