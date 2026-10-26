"""Shared browser setup for the check scripts (journeys, old links, design lock, sense check, browser tests).

Headless Chromium's default user agent contains the word HeadlessChrome. On https://helpmap.uk that
agent is answered with a "Just a moment..." page, and that page keeps a connection open, so a wait
for the network to go idle never finishes. These checks identify as a normal phone or desktop browser.
The agent still contains helpmap-check, which is how the site's own analytics beacon stays off.

A page is opened on domcontentloaded, then — the same way as tests/site_ready.py — when the search
box, the food-bank list and a map pane are on the page. Nothing here waits for networkidle, or for
the load event: a MapTiler tile connection stays open, so both of those waits hang after the page
itself is already there.

A navigation is tried again once only in two cases, and the retry is printed. A dropped connection
is tried again. So is a document that is the site shell but whose core script never ran: the request
failed, Cloudflare (or anyone else) answered it with a challenge or an HTML page, or the HTML was cut
off before data.js. A bot page, a page whose scripts did load but which is still not the app, and any
other error are not tried again.
"""
import time

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
  return {ok:!!document.querySelector('#q')&&n>100&&!!document.querySelector('#map .leaflet-pane')&&!wall,
          n:n,pane:!!document.querySelector('#map .leaflet-pane'),wall:wall,title:title.slice(0,80)}}"""


class BotPage(Exception):
    """The response was a bot interstitial, not the site."""


class AppNotReady(Exception):
    """The document loaded, and it was not the map. Not a network blip."""

    def __init__(self, msg, state=None):
        super().__init__(msg)
        self.state = state or {}


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
    if isinstance(exc, (BotPage, AppNotReady)):
        return False
    s = str(exc)
    if 'networkidle' in s:
        return False
    return any(m in s for m in _BLIPS)


def is_map_tile(url):
    """A map image. MapTiler tile URLs end in .png?key=..., so the query is stripped first."""
    u = (url or '').split('?', 1)[0].split('#', 1)[0]
    hosts = ('api.maptiler.com', 'tile.openstreetmap.org', 'tiles.stadiamaps.com')
    return any(h in u for h in hosts) and u.endswith(('.png', '.jpg', '.webp'))


def new_context(browser, **kw):
    """A browser context with a normal user agent and the shared time limits. Service workers are
    blocked unless the caller asks for them (the old-links check is the one that needs them)."""
    instagram = kw.pop('instagram', False)
    width = (kw.get('viewport') or {}).get('width', 1366)
    kw.setdefault('user_agent', user_agent(width, instagram))
    kw.setdefault('service_workers', 'block')
    c = browser.new_context(**kw)
    c.set_default_timeout(STEP_TIMEOUT)
    c.set_default_navigation_timeout(NAV_TIMEOUT)
    return c


# Scripts the map cannot come up without. A failed image (a tile) is not one of these.
_CORE_SCRIPTS = ('data.js', 'leaflet.js', 'leaflet.markercluster.js', 'tiles.js', 'v3.js', 'layers.js',
                 'icons.js', 'stamp.js', 'access.js', 'register.js', 'report.js')


class _ScriptTraffic:
    """Core script responses for one navigation. A challenge page served as data.js leaves the real
    title in place and never sets FB_DATA, which is the 26 Oct deploy failure."""

    def __init__(self):
        self.bad = []

    def reset(self):
        self.bad = []

    def _core(self, url):
        u = url or ''
        return any(name in u for name in _CORE_SCRIPTS)

    def _cf(self, headers):
        for k, v in (headers or {}).items():
            if k.lower() == 'cf-mitigated':
                return v or 'challenge'
        return ''

    def fail(self, req):
        if getattr(req, 'resource_type', '') != 'script' or not self._core(getattr(req, 'url', '')):
            return
        err = getattr(req, 'failure', '') or ''
        if isinstance(err, dict):
            err = err.get('errorText') or ''
        self.bad.append('failed %s (%s)' % ((req.url or '').split('?')[0][-70:], str(err)[:80]))

    def resp(self, resp):
        req = getattr(resp, 'request', None)
        url = getattr(req, 'url', '') or getattr(resp, 'url', '') or ''
        kind = getattr(req, 'resource_type', '')
        headers = getattr(resp, 'headers', None) or {}
        cf = self._cf(headers)
        if cf and (kind in ('script', 'document') or self._core(url)):
            self.bad.append('cloudflare %s %s' % (cf, url.split('?')[0][-70:]))
            return
        if kind != 'script' or not self._core(url):
            return
        ctype = ''
        try:
            ctype = (headers.get('content-type') or headers.get('Content-Type') or '').lower()
        except Exception:
            ctype = ''
        status = getattr(resp, 'status', 0) or 0
        if status >= 400 or 'html' in ctype:
            self.bad.append('http %s %s %s' % (status, ctype.split(';')[0][:40], url.split('?')[0][-70:]))

    def err(self, error):
        s = str(error).replace('\n', ' ')
        low = s.lower()
        if ('unexpected token' in low or 'syntaxerror' in low or "reading 'items'" in low
                or 'reading "items"' in low or 'd.items' in low or 'failed to fetch' in low):
            self.bad.append('pageerror %s' % s[:140])

    def core_problem(self):
        return bool(self.bad)

    def retry_reason(self):
        if not self.bad:
            return 'document had no data.js (page ended before the scripts)'
        blob = ' '.join(self.bad).lower()
        kind = ('challenge page in place of a script'
                if ('html' in blob or 'cloudflare' in blob or 'just a moment' in blob or 'unexpected token' in blob)
                else 'script failed to load')
        return '%s (%s)' % (kind, '; '.join(self.bad)[:180])

    def suffix(self):
        return (' scripts %s' % '; '.join(self.bad)[:180]) if self.bad else ''


def _arm(page):
    """Listen for script failures once per page. Pages in the unit tests have no `on`."""
    net = getattr(page, '_hm_script_net', None)
    if net is None:
        net = _ScriptTraffic()
        page._hm_script_net = net
        on = getattr(page, 'on', None)
        if on:
            on('requestfailed', net.fail)
            on('response', net.resp)
            on('pageerror', net.err)
    else:
        net.reset()
    return net


def _data_script_missing(page):
    """True only when the parsed document has no data.js tag. A dict from a test double is not missing."""
    try:
        v = page.evaluate("()=>![...document.scripts].some(s=>/data\\.js(?:\\?|$)/.test(s.src||''))")
    except Exception:
        return False
    return v is True


def _should_retry_shell(page, exc, net):
    """The app never started. A page that loaded its scripts and is still wrong is not retried."""
    state = getattr(exc, 'state', None) or {}
    if state.get('wall') or state.get('ok'):
        return False
    if state.get('n') and state.get('pane'):
        return False
    if net.core_problem():
        return True
    return (not state.get('n') and not state.get('pane') and _data_script_missing(page))


def _ready(page, timeout_ms, net=None):
    deadline = time.time() + timeout_ms / 1000.0
    state = {'ok': False, 'wall': False, 'title': ''}
    while time.time() < deadline:
        try:
            state = page.evaluate(APP_READY_JS) or state
        except Exception:
            state = {'ok': False, 'wall': False, 'title': ''}
        if state.get('ok') or state.get('wall'):
            return state
        # data.js / leaflet already failed, or the HTML was cut off. Another 15s will not create the map.
        if (not state.get('n') and not state.get('pane') and net is not None
                and (net.core_problem() or _data_script_missing(page))):
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


def _finish(page, ready, ready_timeout, net=None):
    if ready:
        state = _ready(page, ready_timeout, net)
        if state.get('wall'):
            raise BotPage('bot page instead of the map (%s)' % (state.get('title') or 'Just a moment'))
        if not state.get('ok'):
            raise AppNotReady('app not ready %s%s' % (state, net.suffix() if net else ''), state)
        return
    wall, title = _bot_now(page)
    if wall:
        raise BotPage('bot page instead of the site (%s)' % (title or 'Just a moment')[:80])


def _navigate(page, go, ready, log, ready_timeout):
    """One navigation. A blip, or a shell whose core script never arrived, is tried once more."""
    net = _arm(page)
    last = None
    for attempt in (1, 2):
        try:
            go()
            _finish(page, ready, ready_timeout, net)
            return page
        except BotPage:
            raise
        except AppNotReady as e:
            if attempt == 1 and _should_retry_shell(page, e, net):
                log('retry: %s' % net.retry_reason()[:220])
                net.reset()
                continue
            raise
        except Exception as e:
            last = e
            wall, title = _bot_now(page)
            if wall:
                raise BotPage('bot page instead of the site (%s)' % (title or 'Just a moment')[:80])
            if attempt == 1 and is_network_blip(e):
                log('retry: network blip (%s)' % str(e).splitlines()[0][:180])
                net.reset()
                continue
            raise
    raise last


def goto(page, url, ready=True, log=print, ready_timeout=READY_TIMEOUT):
    """Open url on an existing page. Wait for domcontentloaded, then for the app when ready is set.
    One retry, printed, for a network blip or a shell whose core script never arrived."""
    page.set_default_timeout(STEP_TIMEOUT)
    page.set_default_navigation_timeout(NAV_TIMEOUT)
    return _navigate(
        page, lambda: page.goto(url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT),
        ready, log, ready_timeout)


def reload(page, ready=True, log=print, ready_timeout=READY_TIMEOUT):
    """Reload. Same rule as goto."""
    page.set_default_timeout(STEP_TIMEOUT)
    page.set_default_navigation_timeout(NAV_TIMEOUT)
    return _navigate(
        page, lambda: page.reload(wait_until='domcontentloaded', timeout=NAV_TIMEOUT),
        ready, log, ready_timeout)


def open_page(context, url, ready=True, log=print, ready_timeout=READY_TIMEOUT):
    """A new page. Left open if opening fails, so the caller can record what was on screen."""
    page = context.new_page()
    goto(page, url, ready=ready, log=log, ready_timeout=ready_timeout)
    return page
