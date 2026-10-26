"""Shared browser setup for the check scripts (journeys, old links, design lock, sense check, browser tests).

Headless Chromium's default user agent contains the word HeadlessChrome. On https://helpmap.uk that
agent is answered with a "Just a moment..." page, and that page keeps a connection open, so a wait
for the network to go idle never finishes. These checks identify as a normal phone or desktop browser.
The agent still contains helpmap-check, which is how the site's own analytics beacon stays off.

A page is opened on domcontentloaded, then — the same way as tests/site_ready.py — when the search
box, the food-bank list and a map pane are on the page. Nothing here waits for networkidle, or for
the load event: a MapTiler tile connection stays open, so both of those waits hang after the page
itself is already there.

A navigation is tried again once for a real network blip (the connection failed), and once when
the response was a challenge or an edge block rather than this app. The retry is printed. A page that
loaded and is this app but is not ready, a timeout, and any other error are not tried again. A second
challenge or block is a failure. Tile responses are not a block: a 403 image does not explain a page
that never started, and it must not hide one.
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
  const boot=!!document.querySelector('script[src*="data.js"]');
  return {ok:!!document.querySelector('#q')&&n>100&&!!document.querySelector('#map .leaflet-pane')&&!wall,
          n:n,pane:!!document.querySelector('#map .leaflet-pane'),wall:wall,boot:boot,title:title.slice(0,80)}}"""


class BotPage(Exception):
    """The response was a bot interstitial, not the site."""


class AppNotReady(Exception):
    """The document loaded, and it was not the map. Not a network blip and not a block."""


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


def is_map_tile(url):
    """A map image. MapTiler tile URLs end in .png?key=..., so the query is stripped first."""
    u = (url or '').split('?', 1)[0].split('#', 1)[0]
    hosts = ('api.maptiler.com', 'tile.openstreetmap.org', 'tiles.stadiamaps.com')
    return any(h in u for h in hosts) and u.endswith(('.png', '.jpg', '.webp'))


# An edge or a bot fight. 404 and 500 are this site (a missing file, a broken response) and are not retried.
_BLOCK_STATUSES = (401, 403, 429, 503)
# Scripts whose refusal leaves the map unbuilt. Later scripts (v3.js) run after the pane exists.
_BOOT_SCRIPTS = ('/data.js', '/vendor/leaflet.js')


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
        return BlockedPage('blocked or challenged, not the app %s' % state)
    return AppNotReady('app not ready %s' % state)


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


def _ready(page, timeout_ms, hits=None):
    deadline = time.time() + timeout_ms / 1000.0
    state = {'ok': False, 'wall': False, 'title': ''}
    while time.time() < deadline:
        try:
            state = page.evaluate(APP_READY_JS) or state
        except Exception:
            state = {'ok': False, 'wall': False, 'title': ''}
        # A refused boot script or a document that is not ours will not become the map in this
        # navigation. A page that is ours and merely slow keeps waiting: that is a real failure.
        if state.get('ok') or state.get('wall') or hits or state.get('boot') is False:
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


def _finish(page, ready, ready_timeout, hits):
    if ready:
        err = ready_failure(_ready(page, ready_timeout, hits), hits)
        if err:
            raise err
        return
    wall, title = _bot_now(page)
    if wall:
        raise BotPage('bot page instead of the site (%s)' % (title or 'Just a moment')[:80])
    if hits:
        raise BlockedPage('blocked or challenged page (%s)' % (title or '')[:80])


def _navigate(page, navigate, ready, log, ready_timeout):
    """domcontentloaded, then the app. One logged retry for a network blip or for a challenge/block.
    The same attempt is not used twice: a block followed by a blip is the failure."""
    hits = _block_hits(page)
    page.set_default_timeout(STEP_TIMEOUT)
    page.set_default_navigation_timeout(NAV_TIMEOUT)
    last = None
    for attempt in (1, 2):
        try:
            hits.clear()
            navigate()
            _finish(page, ready, ready_timeout, hits)
            return page
        except (BlockedPage, BotPage) as e:
            last = e
            if attempt == 1:
                log('retry: blocked or challenged (%s)' % str(e).splitlines()[0][:180])
                continue
            raise
        except AppNotReady:
            raise
        except Exception as e:
            last = e
            wall, title = _bot_now(page)
            if wall:
                e = BotPage('bot page instead of the site (%s)' % (title or 'Just a moment')[:80])
                if attempt == 1:
                    log('retry: blocked or challenged (%s)' % str(e).splitlines()[0][:180])
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
