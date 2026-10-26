"""The check scripts share one browser helper. These tests fail on the versions that timed out today
(a wait for networkidle, a HeadlessChrome identity, a tile URL with ?key= ignored, a retry of every
error, and one alert that called every failure an old-links failure) and pass on the helper."""
import os, re, sys, unittest
R = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
import check_browser as B

# Every check that drives the page. A wait for networkidle in any of them is the bug.
CHECK_FILES = [
    'scripts/journeys.py', 'scripts/design_lock.py', 'scripts/old_links.py', 'scripts/sense_check.py',
    'scripts/newlook_parity.py', 'scripts/check_browser.py',
    'tests/test_find_nearest.py', 'tests/test_layer_consistency.py', 'tests/test_list_alignment.py',
    'tests/test_open_today.py', 'tests/test_open_today_toggle.py', 'tests/test_page_accuracy.py',
    'tests/test_place_partial.py', 'tests/test_search_list_top.py', 'tests/test_search_scroll.py',
    'tests/test_status_line.py', 'tests/test_touch_map.py', 'tests/test_two_finger_note.py',
    'tests/test_unverified_label.py',
]
IDLE = re.compile(r"""wait_until\s*=\s*['\"]networkidle['\"]""")
TILE = 'https://api.maptiler.com/maps/streets-v2/256/6/31/20.png?key=abc'


def broken_tile_count(url):
    """The design-lock counter as it was on e45f105: the query string defeated the suffix check,
    and '/tiles/' is not in a MapTiler /maps/ URL. It counted this tile as nothing."""
    return (('api.maptiler.com' in url and '/tiles/' in url)
            or ('api.maptiler.com/maps/' in url and url.endswith(('.png', '.jpg', '.webp'))))


class Helper(unittest.TestCase):
    def test_agents_are_normal_browsers(self):
        for ua in (B.PHONE_UA, B.DESK_UA, B.IG_UA, B.user_agent(390), B.user_agent(1366), B.user_agent(390, instagram=True)):
            self.assertNotIn('HeadlessChrome', ua, ua)
            self.assertIn('helpmap-check', ua)  # the site's beacon skips this, so the checks are not counted
            self.assertFalse(B.looks_like_bot_agent(ua))
        self.assertTrue(B.looks_like_bot_agent('Mozilla/5.0 HeadlessChrome/129.0.6668.29'))
        self.assertIn('Mobile', B.user_agent(390))
        self.assertNotIn('Mobile', B.user_agent(1366))
        self.assertIn('Instagram', B.IG_UA)

    def test_bot_page_detected_and_a_real_title_is_not(self):
        self.assertTrue(B.bot_page('Just a moment...', ''))
        self.assertTrue(B.bot_page('helpmap.uk', 'Performing security verification'))
        self.assertTrue(B.bot_page('', 'checking your browser before accessing'))
        self.assertTrue(B.bot_page('', '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js">'))
        self.assertFalse(B.bot_page('Food banks near you – helpmap.uk', 'Search'))

    def test_only_a_dropped_connection_is_a_blip(self):
        self.assertTrue(B.is_network_blip(Exception('Page.goto: net::ERR_CONNECTION_RESET')))
        self.assertTrue(B.is_network_blip(Exception('net::ERR_NAME_NOT_RESOLVED')))
        self.assertTrue(B.is_network_blip(Exception('net::ERR_EMPTY_RESPONSE')))
        self.assertFalse(B.is_network_blip(Exception('Page.goto: Timeout 30000ms exceeded.\nwaiting until "networkidle"')))
        self.assertFalse(B.is_network_blip(Exception('Page.goto: Timeout 20000ms exceeded')))
        self.assertFalse(B.is_network_blip(Exception('net::ERR_ABORTED')))  # the old worker cancels its own load
        self.assertFalse(B.is_network_blip(B.BotPage('bot page')))
        self.assertFalse(B.is_network_blip(B.AppNotReady('app not ready')))
        self.assertFalse(B.is_network_blip(AssertionError('list not nearest first')))

    def test_maptiler_tile_with_a_key_counts(self):
        self.assertFalse(broken_tile_count(TILE))  # the counter that printed tiles [] 
        self.assertTrue(B.is_map_tile(TILE))
        self.assertTrue(B.is_map_tile('https://tile.openstreetmap.org/6/31/20.png'))
        self.assertFalse(B.is_map_tile('https://helpmap.uk/icon-192.png'))
        self.assertFalse(B.is_map_tile('https://api.maptiler.com/maps/streets-v2/style.json?key=abc'))

    def test_timeouts(self):
        self.assertEqual(B.NAV_TIMEOUT, 20000)
        self.assertEqual(B.STEP_TIMEOUT, 15000)
        self.assertLessEqual(B.READY_TIMEOUT, 20000)


class _Page:
    """Just enough of a Playwright page to drive goto/reload without a browser."""
    def __init__(self, events, state=None, title='Food banks near you'):
        self.events = list(events)  # each goto/reload pops one: Exception or None
        self.state = state or {'ok': True, 'wall': False, 'n': 3000, 'pane': True, 'title': title}
        self.title_text = title
        self.gotos = 0
        self.reloads = 0
        self.body = ''

    def set_default_timeout(self, t):
        pass

    def set_default_navigation_timeout(self, t):
        pass

    def _step(self, kind):
        if kind == 'goto':
            self.gotos += 1
        else:
            self.reloads += 1
        ev = self.events.pop(0)
        if isinstance(ev, Exception):
            raise ev

    def goto(self, url, wait_until='load', timeout=0):
        self.wait_until = wait_until
        self._step('goto')

    def reload(self, wait_until='load', timeout=0):
        self.wait_until = wait_until
        self._step('reload')

    def evaluate(self, js, *a):
        # The ready probe also mentions innerText; only the short bot-page read is the body.
        if js.startswith("()=>(document.body"):
            return self.body
        return self.state

    def title(self):
        return self.title_text

    def wait_for_timeout(self, n):
        pass


class Navigation(unittest.TestCase):
    def test_network_blip_is_retried_once_and_logged(self):
        logs = []
        pg = _Page([Exception('Page.goto: net::ERR_CONNECTION_RESET at https://helpmap.uk/'), None])
        B.goto(pg, 'https://helpmap.uk/?nocount', log=logs.append)
        self.assertEqual(pg.wait_until, 'domcontentloaded')  # load and networkidle both wait on an open tile
        self.assertEqual(pg.gotos, 2)
        self.assertEqual(len(logs), 1)
        self.assertTrue(logs[0].startswith('retry: network blip'), logs)

    def test_a_second_blip_is_the_failure(self):
        logs = []
        pg = _Page([Exception('net::ERR_CONNECTION_RESET'), Exception('net::ERR_CONNECTION_RESET')])
        with self.assertRaises(Exception):
            B.goto(pg, 'https://helpmap.uk/', log=logs.append)
        self.assertEqual(pg.gotos, 2)
        self.assertEqual(len(logs), 1)

    def test_bot_page_is_not_retried(self):
        logs = []
        pg = _Page([None], state={'ok': False, 'wall': True, 'n': 0, 'pane': False, 'title': 'Just a moment...'})
        with self.assertRaises(B.BotPage):
            B.goto(pg, 'https://helpmap.uk/', log=logs.append)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])

    def test_app_not_ready_is_not_retried(self):
        logs = []
        pg = _Page([None], state={'ok': False, 'wall': False, 'n': 0, 'pane': False, 'title': 'helpmap.uk'})
        with self.assertRaises(B.AppNotReady):
            B.goto(pg, 'http://127.0.0.1/', log=logs.append, ready_timeout=300)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])

    def test_a_timeout_is_not_retried(self):
        logs = []
        pg = _Page([Exception('Page.goto: Timeout 20000ms exceeded')])
        with self.assertRaises(Exception):
            B.goto(pg, 'https://helpmap.uk/', log=logs.append)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])

    def test_an_assertion_is_not_a_reason_to_reload(self):
        logs = []
        pg = _Page([AssertionError('nearest first')])
        with self.assertRaises(AssertionError):
            B.goto(pg, 'http://127.0.0.1/', log=logs.append)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])

    def test_reload_logs_one_blip(self):
        logs = []
        pg = _Page([Exception('net::ERR_EMPTY_RESPONSE'), None])
        B.reload(pg, log=logs.append)
        self.assertEqual(pg.reloads, 2)
        self.assertEqual(len(logs), 1)
        self.assertIn('retry: network blip', logs[0])

    def test_area_page_does_not_require_the_map(self):
        logs = []
        pg = _Page([None], state={'ok': False, 'wall': False, 'n': 0, 'pane': False, 'title': 'Food banks in Belfast'})
        B.goto(pg, 'https://helpmap.uk/food-banks/belfast/', ready=False, log=logs.append)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])


class Wired(unittest.TestCase):
    def test_no_check_waits_for_networkidle(self):
        bad = []
        for rel in CHECK_FILES:
            text = open(os.path.join(R, rel), encoding='utf-8').read()
            if IDLE.search(text):
                bad.append(rel)
        self.assertEqual(bad, [])

    def test_live_checks_use_the_helper(self):
        for rel in ('scripts/journeys.py', 'scripts/design_lock.py', 'scripts/old_links.py', 'scripts/sense_check.py'):
            text = open(os.path.join(R, rel), encoding='utf-8').read()
            self.assertIn('check_browser', text, rel)
            self.assertNotIn('HeadlessChrome', text, rel)
        j = open(os.path.join(R, 'scripts', 'journeys.py'), encoding='utf-8').read()
        self.assertNotIn('for attempt in (1, 2)', j)  # that loop retried every error, including a bot page's timeout
        d = open(os.path.join(R, 'scripts', 'design_lock.py'), encoding='utf-8').read()
        self.assertIn('is_map_tile', d)
        self.assertNotIn("user_agent='Mozilla/5.0 helpmap-check'", d)
        o = open(os.path.join(R, 'scripts', 'old_links.py'), encoding='utf-8').read()
        self.assertIn('IG_UA', o)

    def test_deploy_check_names_the_check_that_failed(self):
        y = open(os.path.join(R, '.github', 'workflows', 'deploy-check.yml'), encoding='utf-8').read()
        self.assertNotIn(' && python scripts/journeys.py', y)  # one shell chain hid which check died
        for name in ('steps.oldlinks.outcome', 'steps.journeys.outcome', 'steps.designlock.outcome'):
            self.assertIn(name, y, name)
        self.assertIn('failed check:', y)
        self.assertNotIn('Live old-links check failed', y)  # journeys and design lock were reported under this name

    def test_browser_tests_use_the_same_ready_check_as_pr_94(self):
        # PR 94 (bc3d845a4) waits for the search box, the list and the map pane via tests/site_ready.py.
        # These tests call that helper. A second opener would conflict with that fix.
        ready = open(os.path.join(R, 'tests', 'site_ready.py'), encoding='utf-8').read()
        self.assertIn("document.getElementById('q')", ready)
        self.assertIn('FB_DATA.items.length > 100', ready)
        self.assertIn("#map .leaflet-pane", ready)
        self.assertEqual(ready.split('"""', 2)[-1].count('networkidle'), 0)  # the word only explains the old wait
        self.assertEqual(ready.count('wait_until="domcontentloaded"'), 2)
        live = open(os.path.join(R, 'scripts', 'check_browser.py'), encoding='utf-8').read()
        self.assertIn("querySelector('#q')", live)
        self.assertIn('n>100', live)
        self.assertIn("#map .leaflet-pane", live)
        self.assertIn("wait_until='domcontentloaded'", live)
        for rel in CHECK_FILES:
            if not rel.startswith('tests/test_'):
                continue
            text = open(os.path.join(R, rel), encoding='utf-8').read()
            self.assertIn('from site_ready import', text, rel)
            self.assertIn('open_map(', text, rel)
