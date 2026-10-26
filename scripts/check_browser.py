"""Shared browser setup for the check scripts (journeys, old links, design lock, sense check, browser tests).

Headless Chromium's default user agent contains the word HeadlessChrome. On https://helpmap.uk that
agent is answered with a "Just a moment..." page, and that page keeps a connection open, so a wait
for the network to go idle never finishes. These checks identify as a normal phone or desktop browser.
The agent still contains helpmap-check, which is how the site's own analytics beacon stays off.

A page is opened on domcontentloaded, then — the same way as tests/site_ready.py — when the search
box, the food-bank list and a map pane are on the page. Nothing here waits for networkidle, or for
the load event: a MapTiler tile connection stays open, so both of those waits hang after the page
itself is already there.

A navigation is tried again once only for a real network blip (the connection failed). The retry is
printed. A bot page, a page that loaded but is not the app, and any other error are not tried again.
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


def _ready(page, timeout_ms):
    deadline = time.time() + timeout_ms / 1000.0
    state = {'ok': False, 'wall': False, 'title': ''}
    while time.time() < deadline:
        try:
            state = page.evaluate(APP_READY_JS) or state
        except Exception:
            state = {'ok': False, 'wall': False, 'title': ''}
        if state.get('ok') or state.get('wall'):
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


def _finish(page, ready, ready_timeout):
    if ready:
        state = _ready(page, ready_timeout)
        if state.get('wall'):
            raise BotPage('bot page instead of the map (%s)' % (state.get('title') or 'Just a moment'))
        if not state.get('ok'):
            raise AppNotReady('app not ready %s' % state)
        return
    wall, title = _bot_now(page)
    if wall:
        raise BotPage('bot page instead of the site (%s)' % (title or 'Just a moment')[:80])


def goto(page, url, ready=True, log=print, ready_timeout=READY_TIMEOUT):
    """Open url on an existing page. Wait for domcontentloaded, then for the app when ready is set.
    One retry, and only for a network blip, which is printed."""
    page.set_default_timeout(STEP_TIMEOUT)
    page.set_default_navigation_timeout(NAV_TIMEOUT)
    last = None
    for attempt in (1, 2):
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=NAV_TIMEOUT)
            _finish(page, ready, ready_timeout)
            return page
        except (BotPage, AppNotReady):
            raise
        except Exception as e:
            last = e
            wall, title = _bot_now(page)
            if wall:
                raise BotPage('bot page instead of the site (%s)' % (title or 'Just a moment')[:80])
            if attempt == 1 and is_network_blip(e):
                log('retry: network blip (%s)' % str(e).splitlines()[0][:180])
                continue
            raise
    raise last


def reload(page, ready=True, log=print, ready_timeout=READY_TIMEOUT):
    """Reload. Same rule as goto: domcontentloaded, then the app, and one logged retry for a network blip."""
    page.set_default_timeout(STEP_TIMEOUT)
    page.set_default_navigation_timeout(NAV_TIMEOUT)
    last = None
    for attempt in (1, 2):
        try:
            page.reload(wait_until='domcontentloaded', timeout=NAV_TIMEOUT)
            _finish(page, ready, ready_timeout)
            return page
        except (BotPage, AppNotReady):
            raise
        except Exception as e:
            last = e
            wall, title = _bot_now(page)
            if wall:
                raise BotPage('bot page instead of the site (%s)' % (title or 'Just a moment')[:80])
            if attempt == 1 and is_network_blip(e):
                log('retry: network blip (%s)' % str(e).splitlines()[0][:180])
                continue
            raise
    raise last


def open_page(context, url, ready=True, log=print, ready_timeout=READY_TIMEOUT):
    """A new page. Left open if opening fails, so the caller can record what was on screen."""
    page = context.new_page()
    goto(page, url, ready=ready, log=log, ready_timeout=ready_timeout)
    return page
