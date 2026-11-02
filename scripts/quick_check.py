"""Quick lane for content-only pull requests (2 Nov 2026).

A PR that only changes content (data.js, shelters.js, warmspaces.js, overrides/, data/,
logos/images, generated area pages, notes) gets this instead of the full suite:
  1. syntax: every changed .js passes `node --check`, every changed .json parses;
  2. schema: in a real browser, FB_DATA / SHELTERS / WARMSPACES load, every item has an id,
     a name and UK coordinates, and ids are unique per layer;
  3. smoke render: index.html shows the map and the list with no page errors, and each
     changed area page opens with no page errors.
Anything else in the diff sends the PR down the full suite (see tests.yml `changes`).
Usage: python scripts/quick_check.py FILE...  (the changed files)
"""
import functools, http.server, json, os, subprocess, sys, threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
errors = []

def syntax(files):
    for f in files:
        p = os.path.join(ROOT, f)
        if not os.path.isfile(p):
            continue
        if f.endswith('.js'):
            r = subprocess.run(['node', '--check', p], capture_output=True, text=True)
            if r.returncode:
                errors.append('%s: JS syntax: %s' % (f, r.stderr.strip()[:400]))
        elif f.endswith('.json'):
            try:
                json.load(open(p, encoding='utf-8'))
            except Exception as e:
                errors.append('%s: bad JSON: %s' % (f, e))
    print('syntax: %d file(s) checked' % len(files))

def schema():
    """Every item in each layer has an id and a name, coordinates (when given) inside the UK
    and Channel Islands, and ids are unique per layer. data.full.js is checked on its own."""
    for group in (['data.js', 'shelters.js', 'warmspaces.js'], ['data.full.js']):
        r = subprocess.run(['node', os.path.join(ROOT, 'scripts', 'quick_schema.js')] + [os.path.join(ROOT, f) for f in group],
                           capture_output=True, text=True, cwd=ROOT)
        if r.returncode:
            errors.append('%s: did not load: %s' % (' '.join(group), r.stderr.strip()[-400:])); continue
        out = json.loads(r.stdout)
        print('schema %s: %s' % ('+'.join(group), ', '.join('%s %s' % (k, v.get('n', 'missing')) for k, v in out.items() if not v.get('missing'))))
        want = ('FB_DATA', 'SHELTERS', 'WARMSPACES') if len(group) == 3 else ('FB_DATA',)
        for k in want:
            v = out[k]
            if v.get('missing'): errors.append('%s: %s missing' % (group, k))
            elif v['nbad'] or v['dup']: errors.append('%s: %d bad item(s) %s; duplicate ids %s' % (k, v['nbad'], v['bad'], v['dup']))
            elif v['n'] < 50: errors.append('%s has only %d items' % (k, v['n']))

def render(files):
    from playwright.sync_api import sync_playwright
    from site_ready import open_map
    from check_browser import stub_map_tiles
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    h = functools.partial(Quiet, directory=ROOT)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = 'http://127.0.0.1:%d/' % srv.server_address[1]
    pages = [f for f in files if f.endswith('/index.html') and os.path.isfile(os.path.join(ROOT, f))][:10]
    with sync_playwright() as p:
        b = p.chromium.launch()
        for width in (390, 1366):
            pg = b.new_page(viewport={'width': width, 'height': 800})
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            open_map(pg, base + 'index.html')
            pg.wait_for_timeout(1500)
            if not pg.evaluate("() => !!document.getElementById('list')"): errors.append('index.html %dpx: no list panel' % width)
            errors.extend('index.html %dpx page error: %s' % (width, e) for e in errs)
            pg.close()
        for f in pages:
            pg = b.new_page()
            errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            stub_map_tiles(pg)
            r = pg.goto(base + f, wait_until='domcontentloaded')
            pg.wait_for_timeout(800)
            if not r or r.status != 200: errors.append('%s: HTTP %s' % (f, r and r.status))
            errors.extend('%s page error: %s' % (f, e) for e in errs)
            pg.close()
        b.close()
    srv.shutdown()
    print('smoke render: index.html at 390/1366 px, %d area page(s)' % len(pages))

if __name__ == '__main__':
    files = [f.strip() for f in sys.argv[1:] if f.strip()]
    syntax(files)
    schema()
    render(files)
    for e in errors: print('::error::' + e)
    print('quick check: %s' % ('FAILED (%d)' % len(errors) if errors else 'passed'))
    sys.exit(1 if errors else 0)
