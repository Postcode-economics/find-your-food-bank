"""Old links always load a working site (Dean 25 Oct 11:29/11:31). Runs in CI (local checkout), after each deploy (live) and daily.
For every link ever sent out (scripts/old_links.json) and the forms apps add (?igsh, ?utm_*, ?fbclid, hashes, old paths), with the
Instagram in-app browser UA at 390px: first install an OLD release (service worker + caches; files served from a git snapshot via
request routing), then open the link against the current site and check the map and listings render with no page errors and the
current build. Usage: python scripts/old_links.py [BASE_URL] (default: local checkout). Exit 1 on any failure.
Report: reports/old_links.md + logs/old_links.json."""
import functools, http.server, json, mimetypes, os, subprocess, sys, tempfile, threading
from playwright.sync_api import sync_playwright
import check_browser as B
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
# commit -> must the FIRST open already show the latest build? v80's worker served HTML cache-first, so its first open shows the
# old (working) page and the next open is the latest; v85+ pages carry the self-heal check and must show the latest at once.
OLD_COMMITS = {'3dc505a65': True, '384b862f1': False}   # fyfb-v85 (just before self-heal), fyfb-v80 (week-old Instagram links)
# Dean 25 Oct 18:55: the broken old link was opened from Instagram's in-app browser. iOS uses B.IG_UA
# (the shared agent, so the check is not answered with a bot page). Android is the same check.
IGA = ('Mozilla/5.0 (Linux; Android 14; SM-S911B Build/UP1A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0.6668.100 '
       'Mobile Safari/537.36 Instagram 352.0.0.38.100 Android (34/14; 450dpi; 1080x2340; samsung; SM-S911B; dm1q; qcom; en_GB; 600000000) helpmap-check')
UAS = (('ios', B.IG_UA), ('android', IGA))
CHROME = '/usr/bin/google-chrome' if os.path.exists('/usr/bin/google-chrome') else None

def snapshot(commit):
    d = tempfile.mkdtemp(prefix='old_%s_' % commit)
    subprocess.run('git -C "%s" archive %s | tar -x -C "%s"' % (ROOT, commit, d), shell=True, check=True)
    return d

def links():
    j = json.load(open(os.path.join(ROOT, 'scripts', 'old_links.json'))); return j['sent'] + j['variants']

def cases():
    return [(commit, link, uaname) for commit in OLD_COMMITS for link in links() for uaname, _ in UAS]

def shard(spec=None):
    """OLD_LINKS_SHARD=k/n (CI matrix): every n-th case starting at k. The n shards together are exactly cases()."""
    spec = spec if spec is not None else os.environ.get('OLD_LINKS_SHARD', '')
    if not spec: return cases()
    k, n = (int(x) for x in spec.split('/'))
    if not 1 <= k <= n: raise SystemExit('OLD_LINKS_SHARD %r: need 1 <= k <= n' % spec)
    return cases()[k - 1::n]

def page_ok(pg, link):
    if link.rstrip('/').split('/')[-1] and link.split('?')[0].split('#')[0].count('/') > 1:   # area pages: static listings
        return pg.evaluate("(()=>({ok:document.querySelectorAll('main li,main .card,main a[href^=\"tel:\"],table tr').length>0, why:'area page listings'}))()")
    return pg.evaluate("""(()=>{const pins=document.querySelectorAll('#map .leaflet-marker-icon').length,pane=!!document.querySelector('#map .leaflet-pane');
      const n=typeof items!=='undefined'?items.length:0;return {ok:pane&&pins>0&&n>500,why:'pins '+pins+', items '+n+', map '+pane}})()""")

def run(base=None):
    srv = None
    if not base:
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://localhost:%d' % srv.server_address[1]
    base = base.rstrip('/'); build = json.load(open(os.path.join(ROOT, 'version.json')))['build']
    res = []; todo = shard(); ua_of = dict(UAS)
    print('%d of %d cases%s' % (len(todo), len(cases()), ' (shard %s)' % os.environ['OLD_LINKS_SHARD'] if os.environ.get('OLD_LINKS_SHARD') else ''), flush=True)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME) if CHROME else p.chromium.launch()
        for commit in OLD_COMMITS:
            mine = [(l, (u, ua_of[u])) for c, l, u in todo if c == commit]
            if not mine: continue
            old = snapshot(commit)
            def serve_old(route):
                path = route.request.url.split(base, 1)[-1].split('?')[0].split('#')[0] or '/'
                f = os.path.join(old, path.lstrip('/')); f = os.path.join(f, 'index.html') if os.path.isdir(f) else f
                if not route.request.url.startswith(base) or not os.path.exists(f): return route.continue_()
                route.fulfill(status=200, body=open(f, 'rb').read(), headers={'content-type': mimetypes.guess_type(f)[0] or 'text/html'})
            for link, (uaname, ua) in mine:
                c = B.new_context(b, viewport={'width': 390, 'height': 844}, user_agent=ua, has_touch=True, is_mobile=True, service_workers='allow')
                c.route('**/*', serve_old)
                B.stub_map_tiles(c)  # after the catch-all: continue_() would otherwise send tiles to the network
                pg = c.new_page(); errs = []
                r = dict(old=commit, link=link, ua=uaname)
                try:
                    for _ in range(2):   # install the old release (its own worker may reload the page itself: tolerate aborts)
                        try: pg.goto(base + '/?nocount', wait_until='load', timeout=30000)
                        except Exception: pass
                        pg.wait_for_timeout(3000)
                    try: pg.wait_for_function("!!(navigator.serviceWorker&&navigator.serviceWorker.controller)", timeout=20000); r['old_sw'] = True
                    except Exception: r['old_sw'] = False
                    pg.wait_for_timeout(4000)   # let the old worker finish activating (v83-v86 workers reload their pages)
                    pg.close(); pg = c.new_page()   # fresh tab: an old worker reloading its install tab (v83-v86 did) can't race the test
                    c.unroute('**/*', serve_old); B.stub_map_tiles(c); pg.on('pageerror', lambda e: errs.append(str(e)[:150]))
                    try: B.goto(pg, base + link, ready=False)  # area pages have no map app; a bot page fails this link
                    except B.BotPage as e:
                        r.update(ok=False, why=str(e))
                        res.append(r); print('FAIL', commit, r['ua'], link, r['why'], flush=True); c.close(); continue
                    except Exception as e: r['slow_load'] = str(e)[:80]   # judged by what the visitor sees next, below
                    pg.wait_for_timeout(7000)
                    try: pg.wait_for_function("document.readyState==='complete'", timeout=15000)
                    except Exception: pass
                    st = page_ok(pg, link); r.update(st)
                    if OLD_COMMITS[commit] and link.split('?')[0].split('#')[0] in ('/', '/index.html'):
                        got = pg.evaluate("(document.querySelector('meta[name=helpmap-build]')||{}).content||''")
                        if got != build: r['ok'] = False; r['why'] += ', build %s != %s' % (got, build)
                    if errs: r['ok'] = False; r['why'] += ', errors: ' + '; '.join(errs[:2])
                except Exception as e:
                    r.update(ok=False, why='page hung or failed: %s' % str(e)[:150])
                res.append(r); print('PASS' if r['ok'] else 'FAIL', commit, r.get('ua', ''), link, r['why'], flush=True); c.close()
        b.close()
    if srv: srv.shutdown()
    bad = [r for r in res if not r['ok']]
    os.makedirs(os.path.join(ROOT, 'logs'), exist_ok=True)
    json.dump(res, open(os.path.join(ROOT, 'logs', 'old_links.json'), 'w'), indent=1)
    md = ['# Old links check (%s)' % base, '', '%d of %d passed (old service worker installed first, Instagram in-app UA, 390px).' % (len(res) - len(bad), len(res)), '']
    md += ['- FAIL %s %s: %s' % (r['old'], r['link'], r['why']) for r in bad]
    open(os.path.join(ROOT, 'reports', 'old_links.md'), 'w').write('\n'.join(md) + '\n')
    return res, bad

if __name__ == '__main__':
    res, bad = run(sys.argv[1] if len(sys.argv) > 1 else None)
    sys.exit(1 if bad else 0)
