"""Shared browser setup for the check scripts (journeys, old links, design lock, sense check, browser tests).

Headless Chromium's default user agent contains the word HeadlessChrome. On https://helpmap.uk that
agent is answered with a "Just a moment..." page, and that page keeps a connection open, so a wait
for the network to go idle never finishes. These checks identify as a normal phone or desktop browser.
The agent still contains helpmap-check, which is how the site's own analytics beacon stays off.

A page is opened on domcontentloaded, then — the same way as tests/site_ready.py — when the search
box, the food-bank list and a map pane are on the page. Nothing here waits for networkidle, or for
the load event: a tile connection stays open, so both of those waits hang after the page itself
is already there.

new_context() answers tile hosts with scripts/tile_placeholder.png (HTTP 200) so a check never pans
OpenStreetMap or any other tile server. Set HELPMAP_REAL_TILES=1 to leave that route off. design_lock
still makes one identified tile request of its own and reports that response.

A navigation is tried again once, and the retry is printed. The one retry covers a dropped connection,
a challenge or an edge block, and a core script that never arrived (the request failed, or the response
was a challenge / HTML page, or the HTML was cut off before data.js). It is one retry total: a block
and a script failure do not stack into a second one.

Not tried again: a script error after that file loaded, a 404 or a 500, a timeout, a tile, net::ERR_ABORTED,
and a page whose scripts did load but which is still not the app. A bot page on the retry is a failure.
A copy sw.js serves from its cache is the real app, not a failure; a cache miss is not a pass.
"""
import os, re, time, urllib.error, urllib.request

PHONE_UA = ('Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/129.0.6668.29 Mobile Safari/537.36 helpmap-check')
DESK_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
           'Chrome/129.0.6668.29 Safari/537.36 helpmap-check')
IG_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) '
         'Mobile/15E148 Instagram 330.0.0.0 (iPhone14,5; iOS 17_4; en_GB; en-GB; scale=3.00; 1170x2532; 600000000) helpmap-check')

STEP_TIMEOUT = 15000   # one click, fill or locator
NAV_TIMEOUT = 20000    # domcontentloaded, not the load event and not networkidle
READY_TIMEOUT = 15000  # search box + food-bank data + map pane after the load event

# Connection failures only. A Playwright "Timeout" and net::ERR_ABORTED (a navigation the page
# itself cancelled, which the old service worker does) are not blips and are not retried.
_BLIPS = (
    'net::ERR_CONNECTION_RESET',
    'net::ERR_CONNECTION_CLOSED',
    'net::ERR_CONNECTION_REFUSED',
    'net::ERR_CONNECTION_TIMED_OUT',
    'net::ERR_NAME_NOT_RESOLVED',
    'net::ERR_NETWORK_CHANGED',
    'net::ERR_INTERNET_DISCONNECTED',
    'net::ERR_TIMED_OUT',
    'net::ERR_EMPTY_RESPONSE',
    'net::ERR_SOCKET_NOT_CONNECTED',
    'net::ERR_ADDRESS_UNREACHABLE',
    'NS_ERROR_NET_',
)

APP_READY_JS = """()=>{let n=0;try{n=(window.FB_DATA&&FB_DATA.items&&FB_DATA.items.length)||(typeof items!=='undefined'?items.length:0)}catch(e){}
  const title=document.title||'',body=(document.body&&document.body.innerText||'').slice(0,500);
  const wall=/just a moment|performing security verification|checking your browser|cf-browser-verification/i.test(title+' '+body)
    ||/challenges\\.cloudflare\\.com/.test(document.documentElement.innerHTML.slice(0,2000));
  const boot=!!document.querySelector('script[src*="data.js"]');
  return {ok:!!document.querySelector('#q')&&n>100&&!!document.querySelector('#map .leaflet-pane')&&!wall,
          n:n,pane:!!document.querySelector('#map .leaflet-pane'),wall:wall,boot:boot,title:title.slice(0,80)}}"""


class BotPage(Exception):
    """The response was a bot interstitial, not the site."""


class AppNotReady(Exception):
    """The document loaded, and it was not the map. Not a network blip and not a block."""

    def __init__(self, msg, state=None):
        super().__init__(msg)
        self.state = state or {}


class BlockedPage(Exception):
    """A challenge or an edge block, not this app. One retry, then it is a failure."""


def user_agent(width=1366, instagram=False):
    if instagram:
        return IG_UA
    return PHONE_UA if width < 800 else DESK_UA


def looks_like_bot_agent(ua):
    return 'HeadlessChrome' in (ua or '')


def bot_page(title='', body=''):
    text = '%s %s' % (title or '', (body or '')[:500])
    low = text.lower()
    if 'just a moment' in low or 'performing security verification' in low or 'checking your browser' in low:
        return True
    return 'challenges.cloudflare.com' in low or 'cf-browser-verification' in low


def is_network_blip(exc):
    if isinstance(exc, (BotPage, AppNotReady, BlockedPage)):
        return False
    s = str(exc)
    if 'networkidle' in s:
        return False
    return any(m in s for m in _BLIPS)


# Hosts a map tile can come from. Those in tiles.js (OpenStreetMap, OpenFreeMap, disabled MapTiler), plus hosts a page or an old test might
# still request. Widening this list does not add a provider to the map.
_TILE_HOST = (
    r'(?:[a-z0-9-]+\.)*tile\.openstreetmap\.org'
    r'|api\.maptiler\.com'
    r'|tiles\.stadiamaps\.com'
    r'|tiles\.openfreemap\.org'
    r'|(?:[a-z0-9-]+\.)*basemaps\.cartocdn\.com'
    r'|(?:[a-z0-9-]+\.)*tile\.jawg\.io'
    r'|server\.arcgisonline\.com'
    r'|(?:[a-z0-9-]+\.)*tile\.thunderforest\.com'
)
TILE_RE = re.compile(r'https://(?:%s)/' % _TILE_HOST, re.I)
TILE_PNG = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tile_placeholder.png'), 'rb').read()
def is_map_tile(url):
    """A map tile. The query is stripped first (MapTiler tiles end in .png?key=...).
    style.json and other non-tiles on those hosts are not tiles. A tile path with no
    suffix (ArcGIS /tile/z/y/x) still counts."""
    if not TILE_RE.search(url or ''):
        return False
    path = (url or '').split('?', 1)[0].split('#', 1)[0]
    name = path.rsplit('/', 1)[-1].lower()
    if name.endswith(('.json', '.js', '.css', '.html', '.svg', '.txt')):
        return False
    return True


def stub_map_tiles(target):
    """Fulfill tile-host requests with the bundled placeholder, status 200. No network.

    HELPMAP_REAL_TILES=1 does not register the route. Call this again after unroute(), and
    after any catch-all route(): the later route is the one Playwright uses, and unroute of
    a catch-all can drop this one too.
    """
    if os.environ.get('HELPMAP_REAL_TILES') == '1':
        return False

    def _stub(route):
        route.fulfill(status=200, content_type='image/png', body=TILE_PNG, headers={
            'access-control-allow-origin': '*',
            'cache-control': 'public, max-age=604800',
            'x-helpmap-tile': 'stub',
        })

    target.route(TILE_RE, _stub)
    return True


# An edge or a bot fight. 404 and 500 are this site (a missing file, a broken response) and are not retried.
_BLOCK_STATUSES = (401, 403, 429, 503)
# Scripts whose refusal leaves the map unbuilt. Later scripts (v3.js) run after the pane exists.
_BOOT_SCRIPTS = ('/data.js', '/vendor/leaflet.js')
# Everything the map boots from. A failed image (a tile) is not one of these.
_CORE_SCRIPTS = ('data.js', 'leaflet.js', 'leaflet.markercluster.js', 'tiles.js', 'v3.js', 'layers.js',
                 'icons.js', 'stamp.js', 'access.js', 'register.js', 'report.js')


def is_external_block(status, url, resource_type=''):
    """True when an edge refused the document or a boot script. A tile 403 is not one: the pane
    exists before any tile returns, and a tile error must not turn a broken app into a retry."""
    try:
        status = int(status)
    except (TypeError, ValueError):
        return False
    if status not in _BLOCK_STATUSES or is_map_tile(url):
        return False
    if (resource_type or '') == 'document':
        return True
    path = (url or '').split('?', 1)[0].split('#', 1)[0]
    return any(bit in path for bit in _BOOT_SCRIPTS)


def ready_failure(state, hits):
    """BotPage, BlockedPage, AppNotReady, or None when the app is up. hits are this attempt's blocks."""
    state = state or {}
    if state.get('ok'):
        return None
    if state.get('wall'):
        return BotPage('bot page instead of the map (%s)' % (state.get('title') or 'Just a moment'))
    # boot False: the HTML has no data.js, so this is not our document (a challenge that kept the
    # title, or a block page). boot missing means the probe did not say, and that stays a real failure.
    if hits or state.get('boot') is False:
        msg = 'blocked or challenged, not the app %s' % state
        if state.get('boot') is False:
            msg = 'document had no data.js (page ended before the scripts); ' + msg
        return BlockedPage(msg)
    return AppNotReady('app not ready %s' % state, state)


class _ScriptTraffic:
    """Core script responses for one navigation. A challenge page served as data.js leaves the real
    title in place and never sets FB_DATA. A 200 that sw.js answered from cache is the script that ran."""

    def __init__(self):
        self.bad = []    # (url, message) retryable misses
        self.hard = []   # (url, message) 404 / 500, never retried
        self.served = set()

    def reset(self):
        self.bad = []
        self.hard = []
        self.served = set()

    def _core(self, url):
        return any(name in (url or '') for name in _CORE_SCRIPTS)

    def _key(self, url):
        return (url or '').split('?', 1)[0]

    def _cf(self, headers):
        for k, v in (headers or {}).items():
            if str(k).lower() == 'cf-mitigated':
                return v or 'challenge'
        return ''

    def _drop(self, key):
        """A successful copy of this URL arrived (network or the service worker cache)."""
        self.served.add(key)
        self.bad = [(u, m) for u, m in self.bad if u != key]
        self.hard = [(u, m) for u, m in self.hard if u != key]

    def fail(self, req):
        if getattr(req, 'resource_type', '') != 'script' or not self._core(getattr(req, 'url', '')):
            return
        key = self._key(getattr(req, 'url', ''))
        if key in self.served or any(u == key for u, _ in self.bad):
            return
        err = getattr(req, 'failure', '') or ''
        if callable(err):
            try:
                err = err() or ''
            except Exception:
                err = ''
        if isinstance(err, dict):
            err = err.get('errorText') or ''
        self.bad.append((key, 'failed %s (%s)' % (key[-70:], str(err)[:80])))

    def resp(self, resp):
        req = getattr(resp, 'request', None)
        url = getattr(req, 'url', '') or getattr(resp, 'url', '') or ''
        key = self._key(url)
        kind = getattr(req, 'resource_type', '') if req is not None else ''
        headers = getattr(resp, 'headers', None) or {}
        cf = self._cf(headers)
        if cf and key not in self.served and (kind in ('script', 'document') or self._core(url)):
            self.bad.append((key, 'cloudflare %s %s' % (cf, key[-70:])))
            return
        if kind != 'script' or not self._core(url):
            return
        try:
            ctype = (headers.get('content-type') or headers.get('Content-Type') or '').lower()
        except Exception:
            ctype = ''
        status = getattr(resp, 'status', 0) or 0
        if status in (404, 500):
            if key not in self.served:
                self.hard.append((key, 'http %s %s' % (status, key[-70:])))
            return
        if status >= 400 or 'html' in ctype:
            if key not in self.served and not any(u == key for u, _ in self.bad):
                self.bad.append((key, 'http %s %s %s' % (status, ctype.split(';')[0][:40], key[-70:])))
            return
        if status and status < 400:
            self._drop(key)

    def err(self, error):
        s = str(error).replace('\n', ' ')
        low = s.lower()
        if ('unexpected token' in low or 'syntaxerror' in low or "reading 'items'" in low
                or 'reading "items"' in low or 'd.items' in low or 'failed to fetch' in low):
            self.bad.append(('pageerror', 'pageerror %s' % s[:140]))

    def _retryable(self):
        """Misses that one more navigation might clear. A throw after the file loaded is ours.
        Chromium also reports a 404 or 500 script as net::ERR_ABORTED; the status is the real failure
        and that abort must not become a retry."""
        hard_urls = {u for u, _ in self.hard}
        out = []
        for url, msg in self.bad:
            if url in self.served or url in hard_urls:
                continue
            if msg.startswith('pageerror ') and self.served:
                continue
            out.append((url, msg))
        return out

    def hard_open(self):
        return [(u, m) for u, m in self.hard if u not in self.served]

    def core_problem(self):
        return bool(self._retryable())

    def definitive(self, sw_controlled):
        """Stop waiting. A bare network failure under a controlling service worker is not definitive:
        sw.js still has the precached data.js and leaflet.js to answer with."""
        if self.hard_open():
            return True
        open_bad = self._retryable()
        if not open_bad:
            return False
        if sw_controlled and all(m.startswith('failed ') or m.startswith('pageerror ') for _, m in open_bad):
            return False
        return True

    def retry_reason(self):
        msgs = [m for _, m in self._retryable()]
        if not msgs:
            return 'document had no data.js (page ended before the scripts)'
        blob = ' '.join(msgs).lower()
        kind = ('challenge page in place of a script'
                if ('html' in blob or 'cloudflare' in blob or 'just a moment' in blob or 'unexpected token' in blob)
                else 'script failed to load')
        return '%s (%s)' % (kind, '; '.join(msgs)[:180])

    def suffix(self):
        msgs = [m for _, m in self._retryable()]
        return (' scripts %s' % '; '.join(msgs)[:180]) if msgs else ''


def _block_hits(page):
    """Statuses seen on this page. Attached once; each navigation clears the list itself."""
    hits = getattr(page, '_hm_block_hits', None)
    if hits is None:
        hits = []
        page._hm_block_hits = hits
        on = getattr(page, 'on', None)
        if on:
            def on_response(resp):
                try:
                    kind = ''
                    try:
                        kind = resp.request.resource_type or ''
                    except Exception:
                        kind = ''
                    if is_external_block(resp.status, resp.url, kind):
                        hits.append((resp.status, resp.url))
                except Exception:
                    pass
            try:
                on('response', on_response)
            except Exception:
                pass
    return hits


def _arm(page):
    """Listen for script failures once per page. Pages in the unit tests have no `on` until they opt in."""
    net = getattr(page, '_hm_script_net', None)
    if net is None:
        net = _ScriptTraffic()
        page._hm_script_net = net
        on = getattr(page, 'on', None)
        if on:
            on('requestfailed', net.fail)
            on('response', net.resp)
            on('pageerror', net.err)
    return net


def _data_script_missing(page):
    """True only when the parsed document has no data.js tag. A dict from a test double is not missing."""
    try:
        v = page.evaluate("()=>![...document.scripts].some(s=>/data\\.js(?:\\?|$)/.test(s.src||''))")
    except Exception:
        return False
    return v is True


def _sw_controlled(page):
    """True when this page's service worker will answer a failed fetch from cache."""
    try:
        v = page.evaluate("()=>!!(navigator.serviceWorker&&navigator.serviceWorker.controller)")
    except Exception:
        return False
    return v is True


def _should_retry_shell(page, exc, net):
    """The app never started because a core script did not arrive. A page that loaded its scripts is not retried."""
    state = getattr(exc, 'state', None) or {}
    if state.get('wall') or state.get('ok'):
        return False
    if state.get('n') and state.get('pane'):
        return False
    if net is not None and net.core_problem():
        return True
    return (not state.get('n') and not state.get('pane') and _data_script_missing(page))


def new_context(browser, **kw):
    """A browser context with a normal user agent and the shared time limits. Service workers are
    blocked unless the caller asks for them (the old-links check is the one that needs them).
    Tile hosts are stubbed unless HELPMAP_REAL_TILES=1."""
    instagram = kw.pop('instagram', False)
    width = (kw.get('viewport') or {}).get('width', 1366)
    kw.setdefault('user_agent', user_agent(width, instagram))
    kw.setdefault('service_workers', 'block')
    c = browser.new_context(**kw)
    c.set_default_timeout(STEP_TIMEOUT)
    c.set_default_navigation_timeout(NAV_TIMEOUT)
    stub_map_tiles(c)
    return c


def _ready(page, timeout_ms, hits=None, net=None):
    deadline = time.time() + timeout_ms / 1000.0
    state = {'ok': False, 'wall': False, 'title': ''}
    while time.time() < deadline:
        try:
            state = page.evaluate(APP_READY_JS) or state
        except Exception:
            state = {'ok': False, 'wall': False, 'title': ''}
        if state.get('ok') or state.get('wall'):
            return state
        # A document that is not ours will not grow a data.js tag. A refused boot script will not
        # become the map either, unless a controlling service worker still has the cached copy
        # (the network attempt fails, then sw.js answers). That case keeps waiting.
        if state.get('boot') is False or _data_script_missing(page):
            return state
        sw = _sw_controlled(page)
        if hits and not sw:
            return state
        if (not state.get('n') and not state.get('pane') and net is not None and net.definitive(sw)):
            return state
        page.wait_for_timeout(250)
    return state


def _bot_now(page):
    title, body = '', ''
    try:
        title = page.title() or ''
    except Exception:
        pass
    try:
        body = page.evaluate("()=>(document.body&&document.body.innerText||'').slice(0,500)") or ''
    except Exception:
        pass
    return bot_page(title, body), title


def _finish(page, ready, ready_timeout, hits, net):
    if ready:
        state = _ready(page, ready_timeout, hits, net) or {}
        if not state.get('ok') and not state.get('wall') and state.get('boot') is not False and _data_script_missing(page):
            state = dict(state)
            state['boot'] = False
        err = ready_failure(state, hits)
        if isinstance(err, AppNotReady) and net is not None:
            extra = net.suffix()
            if extra:
                err = AppNotReady('%s%s' % (err, extra), state)
        if err:
            raise err
        return
    wall, title = _bot_now(page)
    if wall:
        raise BotPage('bot page instead of the site (%s)' % (title or 'Just a moment')[:80])
    if hits:
        raise BlockedPage('blocked or challenged page (%s)' % (title or '')[:80])


def _navigate(page, navigate, ready, log, ready_timeout):
    """domcontentloaded, then the app. One logged retry for a blip, a challenge/block, or a core script
    that never arrived. The same attempt is not used twice: a block followed by a blip is the failure."""
    hits = _block_hits(page)
    net = _arm(page)
    page.set_default_timeout(STEP_TIMEOUT)
    page.set_default_navigation_timeout(NAV_TIMEOUT)
    last = None
    for attempt in (1, 2):
        try:
            hits.clear()
            net.reset()
            navigate()
            _finish(page, ready, ready_timeout, hits, net)
            return page
        except (BlockedPage, BotPage) as e:
            last = e
            if attempt == 1:
                log('retry: blocked or challenged (%s)' % str(e).splitlines()[0][:300])
                continue
            raise
        except AppNotReady as e:
            if attempt == 1 and _should_retry_shell(page, e, net):
                log('retry: %s' % net.retry_reason()[:220])
                continue
            raise
        except Exception as e:
            last = e
            wall, title = _bot_now(page)
            if wall:
                e = BotPage('bot page instead of the site (%s)' % (title or 'Just a moment')[:80])
                if attempt == 1:
                    log('retry: blocked or challenged (%s)' % str(e).splitlines()[0][:300])
                    continue
                raise e
            if attempt == 1 and is_network_blip(e):
                log('retry: network blip (%s)' % str(e).splitlines()[0][:180])
                continue
            raise
    raise last


def goto(page, url, ready=True, log=print, ready_timeout=READY_TIMEOUT):
    """Open url on an existing page. Wait for domcontentloaded, then for the app when ready is set."""
    return _navigate(page, lambda: page.goto(url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT),
                     ready, log, ready_timeout)


def reload(page, ready=True, log=print, ready_timeout=READY_TIMEOUT):
    """Reload. Same rule as goto."""
    return _navigate(page, lambda: page.reload(wait_until='domcontentloaded', timeout=NAV_TIMEOUT),
                     ready, log, ready_timeout)


def open_page(context, url, ready=True, log=print, ready_timeout=READY_TIMEOUT):
    """A new page. Left open if opening fails, so the caller can record what was on screen."""
    page = context.new_page()
    goto(page, url, ready=ready, log=log, ready_timeout=ready_timeout)
    return page
