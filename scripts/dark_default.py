"""Dark-by-default check. Usage: python scripts/dark_default.py [BASE_URL] [--webkit].

The v89 copy called the browser's own new_context directly, so it never picked up the shared tile stub and a run
could pan a tile host. This uses check_browser.new_context, which serves the placeholder tile unless
HELPMAP_REAL_TILES=1.

The page on main follows the visitor's saved Light mode choice. With no saved choice it follows
the prefers-colour-scheme media query (headless Chrome reports that query as light when the
context asks for no-preference). The v89 page ignored a light OS scheme; that change was reverted.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_browser as B

BLOCK = "for(const k of ['localStorage','sessionStorage'])Object.defineProperty(window,k,{get(){throw new DOMException('denied','SecurityError')}});"


def _want_light(scheme, case):
    if case == 'saved-light':
        return True
    if case == 'saved-dark':
        return False
    # no saved choice: follow the OS query. This Chrome reports no-preference as light.
    return scheme != 'dark'


def run(base, engines):
    bad = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        for eng in engines:
            try:
                kw = {'executable_path': '/usr/bin/google-chrome'} if eng == 'chromium' and os.path.exists('/usr/bin/google-chrome') else {}
                b = getattr(p, eng).launch(**kw)
            except Exception as e:
                bad.append((eng, 'cannot launch: %s' % str(e)[:80]))
                continue
            for scheme in ('light', 'no-preference', 'dark'):
                for case in ('fresh', 'blocked', 'saved-light', 'saved-dark'):
                    kw = dict(color_scheme=scheme, viewport={'width': 390, 'height': 844})
                    if case == 'blocked':
                        kw['user_agent'] = B.IG_UA
                    c = B.new_context(b, **kw)
                    if case == 'blocked':
                        c.add_init_script(BLOCK)
                    if case.startswith('saved'):
                        c.add_init_script("try{if(!sessionStorage.getItem('dd')){sessionStorage.setItem('dd','1');localStorage.setItem('light','%s')}}catch(e){}" % ('1' if case == 'saved-light' else '0'))
                    pg = c.new_page()
                    try:
                        B.goto(pg, base.rstrip('/') + '/?nocount')
                        light = pg.evaluate("document.documentElement.classList.contains('light')")
                        bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
                    except Exception as e:
                        light, bg = None, 'error %s' % str(e)[:60]
                    want = _want_light(scheme, case)
                    ok = light is want
                    print('PASS' if ok else 'FAIL', eng, scheme, case, 'light' if light else 'dark', bg, flush=True)
                    if not ok:
                        bad.append((eng, scheme, case, light, bg))
                    c.close()
            b.close()
    return bad


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    base = (a[0] if a else 'https://helpmap.uk').rstrip('/')
    bad = run(base, ['chromium'] + (['webkit'] if '--webkit' in sys.argv else []))
    print('dark default: %d problem(s)' % len(bad))
    sys.exit(1 if bad else 0)
