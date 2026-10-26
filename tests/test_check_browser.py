"""The check scripts share one browser helper. These tests fail on the versions that timed out today
(a wait for networkidle, a HeadlessChrome identity, a tile URL with ?key= ignored, a retry of every
error, and one alert that called every failure an old-links failure) and pass on the helper."""
import os, re, sys, unittest
R = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(R, 'scripts'))
import check_browser as B

# Every check that drives the page. A wait for networkidle in any of them is the bug.
CHECK_FILES = [
    'scripts/journeys.py', 'scripts/design_lock.py', 'scripts/old_links.py', 'scripts/dark_default.py', 'scripts/sense_check.py',
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
        self.assertFalse(B.is_network_blip(B.BlockedPage('blocked')))
        self.assertFalse(B.is_network_blip(AssertionError('list not nearest first')))

    def test_only_an_edge_block_of_the_document_or_a_boot_script_is_inconclusive(self):
        tile = 'http://127.0.0.1/tile.openstreetmap.org/5/15/9.png'
        self.assertTrue(B.is_map_tile(tile))  # same-origin path still a tile, so the test never calls a tile server
        self.assertFalse(B.is_external_block(403, tile, 'image'))
        self.assertFalse(B.is_external_block(403, 'https://tile.openstreetmap.org/6/31/20.png', 'image'))
        self.assertFalse(B.is_external_block(200, 'http://127.0.0.1/data.js', 'script'))
        self.assertFalse(B.is_external_block(404, 'http://127.0.0.1/data.js?v=1', 'script'))  # our missing file
        self.assertFalse(B.is_external_block(500, 'http://127.0.0.1/data.js', 'script'))
        self.assertFalse(B.is_external_block(403, 'http://127.0.0.1/v3.js', 'script'))  # runs after the pane exists
        self.assertFalse(B.is_external_block(403, 'http://127.0.0.1/icon-192.png', 'image'))
        self.assertTrue(B.is_external_block(403, 'http://127.0.0.1/data.js?v=1', 'script'))
        self.assertTrue(B.is_external_block(429, 'http://127.0.0.1/vendor/leaflet.js', 'script'))
        self.assertTrue(B.is_external_block(503, 'http://127.0.0.1/?nocount', 'document'))
        self.assertTrue(B.is_external_block(401, 'http://127.0.0.1/', 'document'))
        broken = {'ok': False, 'wall': False, 'n': 0, 'pane': False, 'boot': True, 'title': 'helpmap.uk'}
        self.assertIsInstance(B.ready_failure(broken, []), B.AppNotReady)
        self.assertIsInstance(B.ready_failure({'ok': False, 'n': 0, 'pane': False, 'title': 'helpmap.uk'}, []), B.AppNotReady)
        self.assertIsNone(B.ready_failure({'ok': True, 'wall': False, 'boot': True}, [(403, 'http://127.0.0.1/data.js')]))
        challenged = {'ok': False, 'wall': False, 'n': 0, 'pane': False, 'boot': False,
                      'title': 'Find a food bank, warm space or shelter near you – helpmap.uk'}
        self.assertIsInstance(B.ready_failure(challenged, []), B.BlockedPage)
        self.assertIsInstance(B.ready_failure(broken, [(403, 'http://127.0.0.1/data.js')]), B.BlockedPage)
        self.assertIsInstance(B.ready_failure({'ok': False, 'wall': True, 'title': 'Just a moment...'}, []), B.BotPage)

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
        self.navs = 0
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
        self.navs += 1
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
        if isinstance(self.state, list):
            return self.state[min(self.navs, len(self.state)) - 1]
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

    def test_a_challenge_is_retried_once_and_a_second_challenge_fails(self):
        logs = []
        wall = {'ok': False, 'wall': True, 'n': 0, 'pane': False, 'title': 'Just a moment...'}
        pg = _Page([None, None], state=wall)
        with self.assertRaises(B.BotPage):
            B.goto(pg, 'http://127.0.0.1/', log=logs.append)
        self.assertEqual(pg.gotos, 2)
        self.assertEqual(len(logs), 1)
        self.assertIn('retry: blocked or challenged', logs[0])

    def test_a_challenge_then_the_app_is_not_a_failure(self):
        logs = []
        wall = {'ok': False, 'wall': True, 'n': 0, 'pane': False, 'boot': False, 'title': 'Just a moment...'}
        good = {'ok': True, 'wall': False, 'n': 3000, 'pane': True, 'boot': True, 'title': 'Food banks near you'}
        pg = _Page([None, None], state=[wall, good])
        B.goto(pg, 'http://127.0.0.1/', log=logs.append)
        self.assertEqual(pg.gotos, 2)
        self.assertEqual(len(logs), 1)

    def test_a_replaced_page_is_retried_once_then_fails(self):
        # The 11:07 log: real title, n=0, pane=False, wall=False. With no data.js tag this is not our document.
        logs = []
        replaced = {'ok': False, 'wall': False, 'n': 0, 'pane': False, 'boot': False,
                    'title': 'Find a food bank, warm space or shelter near you – helpmap.uk'}
        pg = _Page([None, None], state=replaced)
        with self.assertRaises(B.BlockedPage):
            B.goto(pg, 'http://127.0.0.1/', log=logs.append, ready_timeout=200)
        self.assertEqual(pg.gotos, 2)
        self.assertEqual(len(logs), 1)
        self.assertIn('blocked or challenged', logs[0])
        self.assertIn('no data.js', logs[0])

    def test_app_not_ready_is_not_retried(self):
        # boot True: our HTML, scripts returned, the map still did not come up. That is our failure.
        # Scripts loaded (the double reports no script failure and the data.js tag is not missing).
        logs = []
        pg = _Page([None], state={'ok': False, 'wall': False, 'n': 0, 'pane': False, 'boot': True, 'title': 'helpmap.uk'})
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

    def test_reload_retries_a_challenge_once(self):
        logs = []
        wall = {'ok': False, 'wall': True, 'n': 0, 'pane': False, 'title': 'Just a moment...'}
        pg = _Page([None, None], state=wall)
        with self.assertRaises(B.BotPage):
            B.reload(pg, log=logs.append)
        self.assertEqual(pg.reloads, 2)
        self.assertEqual(len(logs), 1)

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


class _Req:
    def __init__(self, url, resource_type='script', failure=None, status=200, content_type='text/javascript'):
        self.url = url
        self.resource_type = resource_type
        self.failure = failure
        self.status = status
        self.headers = {'content-type': content_type}
        self.request = self


class _Shell(_Page):
    """A page double that can report a failed core script, then a good load."""

    def __init__(self, states, problems, missing=None):
        super().__init__([None] * len(states))
        self.states = list(states)
        self.problems = list(problems)
        self.missing_flags = list(missing or [False] * len(states))
        self.handlers = {}

    def on(self, ev, fn):
        self.handlers.setdefault(ev, []).append(fn)

    def goto(self, url, wait_until='load', timeout=0):
        self.wait_until = wait_until
        self._step('goto')
        self.state = self.states[self.gotos - 1]
        self.missing = self.missing_flags[self.gotos - 1]
        for ev, obj in self.problems[self.gotos - 1]:
            for fn in self.handlers.get(ev, []):
                fn(obj)

    def evaluate(self, js, *a):
        if js.startswith("()=>(document.body"):
            return self.body
        if 'document.scripts' in js:
            return self.missing
        return self.state


class _DelayedReady(_Shell):
    """Ready probe stays down for a few polls, so an early exit on a script failure is visible."""

    def __init__(self, problems, sw=False, ready_after=3, stay_down=False):
        n = len(problems)
        super().__init__([_NOT_READY] * n, problems, missing=[False] * n)
        self.sw = sw
        self.ready_after = ready_after
        self.stay_down = stay_down
        self.probes = 0

    def goto(self, url, wait_until='load', timeout=0):
        self.probes = 0
        super().goto(url, wait_until=wait_until, timeout=timeout)

    def evaluate(self, js, *a):
        if js.startswith("()=>(document.body"):
            return self.body
        if 'document.scripts' in js:
            return False
        if 'serviceWorker' in js:
            return self.sw
        if js.startswith('()=>{'):
            self.probes += 1
            if self.stay_down or self.probes < self.ready_after:
                down = dict(_NOT_READY)
                down['boot'] = True
                return down
            return dict(_READY)
        return super().evaluate(js, *a)


_NOT_READY = {'ok': False, 'wall': False, 'n': 0, 'pane': False,
              'title': 'Find a food bank, warm space or shelter near you – helpmap.uk'}
_READY = {'ok': True, 'wall': False, 'n': 3000, 'pane': True, 'title': _NOT_READY['title']}


class ScriptNeverArrived(unittest.TestCase):
    """Run 40305441261: the document title was the real site, wall was false, and the map never
    started (n 0, no pane). That is a core script that did not run, not a theme failure."""

    def test_a_failed_data_script_is_retried_once_and_logged(self):
        logs = []
        pg = _Shell(
            [_NOT_READY, _READY],
            [[('requestfailed', _Req('https://helpmap.uk/data.js?v=1', failure='net::ERR_CONNECTION_RESET'))], []])
        B.goto(pg, 'https://helpmap.uk/?nocount', log=logs.append, ready_timeout=3000)
        self.assertEqual(pg.gotos, 2)
        self.assertEqual(len(logs), 1)
        self.assertIn('retry: script failed to load', logs[0])
        self.assertIn('data.js', logs[0])

    def test_html_in_place_of_a_script_is_a_challenge_and_retried_once(self):
        logs = []
        pg = _Shell(
            [_NOT_READY, _READY],
            [[('response', _Req('https://helpmap.uk/data.js?v=1', status=200, content_type='text/html; charset=UTF-8'))], []])
        B.goto(pg, 'https://helpmap.uk/?nocount', log=logs.append, ready_timeout=3000)
        self.assertEqual(pg.gotos, 2)
        self.assertIn('retry: challenge page in place of a script', logs[0])

    def test_a_script_that_keeps_failing_is_still_a_failure(self):
        logs = []
        bad = ('response', _Req('https://helpmap.uk/data.js?v=1', status=200, content_type='text/html'))
        pg = _Shell([_NOT_READY, _NOT_READY], [[bad], [bad]])
        with self.assertRaises(B.AppNotReady) as cm:
            B.goto(pg, 'https://helpmap.uk/?nocount', log=logs.append, ready_timeout=3000)
        self.assertEqual(pg.gotos, 2)  # once, not a loop
        self.assertEqual(len(logs), 1)
        self.assertIn('data.js', str(cm.exception))

    def test_a_page_cut_off_before_data_js_is_retried_once(self):
        logs = []
        pg = _Shell([_NOT_READY, _READY], [[], []], missing=[True, False])
        B.goto(pg, 'https://helpmap.uk/?nocount', log=logs.append, ready_timeout=3000)
        self.assertEqual(pg.gotos, 2)
        self.assertIn('no data.js', logs[0])

    def test_a_loaded_page_that_is_not_the_app_is_not_retried_even_with_listeners(self):
        logs = []
        pg = _Shell([_NOT_READY], [[]])
        with self.assertRaises(B.AppNotReady):
            B.goto(pg, 'https://helpmap.uk/?nocount', log=logs.append, ready_timeout=300)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])

    def test_a_bot_page_is_still_not_retried_when_a_script_failed(self):
        # Combined path: a bot page is the one block retry. A failed script on that page does not
        # add another retry, and the bot page that comes back on the retry is still a failure.
        logs = []
        wall = {'ok': False, 'wall': True, 'n': 0, 'pane': False, 'title': 'Just a moment...'}
        bad = ('requestfailed', _Req('https://helpmap.uk/data.js', failure='net::ERR_FAILED'))
        pg = _Shell([wall, wall], [[bad], [bad]])
        with self.assertRaises(B.BotPage):
            B.goto(pg, 'https://helpmap.uk/', log=logs.append, ready_timeout=3000)
        self.assertEqual(pg.gotos, 2)
        self.assertEqual(len(logs), 1)
        self.assertIn('retry: blocked or challenged', logs[0])

    def test_tiles_are_not_a_reason_to_retry(self):
        logs = []
        # The map is up. A tile request dying must not be treated as the app failing to load.
        ready = dict(_READY)
        pg = _Shell(
            [ready],
            [[('requestfailed', _Req('https://tile.openstreetmap.org/6/31/20.png', resource_type='image',
                                     failure='net::ERR_BLOCKED_BY_RESPONSE'))]])
        B.goto(pg, 'https://helpmap.uk/?nocount', log=logs.append, ready_timeout=3000)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])

    def test_a_404_script_is_a_real_failure_with_no_retry(self):
        logs = []
        # Chromium reports the 404 and then net::ERR_ABORTED for the same script. The abort is not a retry.
        pg = _Shell([_NOT_READY], [[
            ('response', _Req('https://helpmap.uk/data.js?v=1', status=404)),
            ('requestfailed', _Req('https://helpmap.uk/data.js?v=1', failure='net::ERR_ABORTED')),
        ]])
        with self.assertRaises(B.AppNotReady):
            B.goto(pg, 'http://127.0.0.1/', log=logs.append, ready_timeout=500)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])

    def test_a_500_script_is_a_real_failure_with_no_retry(self):
        logs = []
        pg = _Shell([_NOT_READY], [[
            ('response', _Req('https://helpmap.uk/data.js?v=1', status=500)),
            ('requestfailed', _Req('https://helpmap.uk/data.js?v=1', failure='net::ERR_ABORTED')),
        ]])
        with self.assertRaises(B.AppNotReady):
            B.goto(pg, 'http://127.0.0.1/', log=logs.append, ready_timeout=500)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])

    def test_a_script_error_after_the_file_loaded_is_not_retried(self):
        logs = []
        pg = _Shell(
            [_NOT_READY],
            [[
                ('response', _Req('https://helpmap.uk/data.js?v=1', status=200)),
                ('pageerror', Exception("TypeError: Cannot read properties of undefined (reading 'items')")),
            ]])
        with self.assertRaises(B.AppNotReady):
            B.goto(pg, 'http://127.0.0.1/', log=logs.append, ready_timeout=400)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])

    def test_a_script_error_when_nothing_loaded_is_retried_once(self):
        logs = []
        err = ('pageerror', Exception("TypeError: Cannot read properties of undefined (reading 'items')"))
        pg = _Shell([_NOT_READY, _READY], [[err], []])
        B.goto(pg, 'https://helpmap.uk/?nocount', log=logs.append, ready_timeout=3000)
        self.assertEqual(pg.gotos, 2)
        self.assertEqual(len(logs), 1)
        self.assertIn('retry: script failed to load', logs[0])

    def test_a_served_copy_after_a_failed_fetch_is_not_a_failure(self):
        # Network attempt dies, then the cached bytes are the response that runs. One navigation.
        logs = []
        fail = ('requestfailed', _Req('https://helpmap.uk/data.js?v=1', failure='net::ERR_FAILED'))
        ok = ('response', _Req('https://helpmap.uk/data.js?v=1', status=200))
        leaf_fail = ('requestfailed', _Req('https://helpmap.uk/vendor/leaflet.js', failure='net::ERR_FAILED'))
        leaf_ok = ('response', _Req('https://helpmap.uk/vendor/leaflet.js', status=200))
        pg = _DelayedReady([[fail, ok, leaf_fail, leaf_ok]], sw=False, ready_after=3)
        B.goto(pg, 'http://127.0.0.1/?nocount', log=logs.append, ready_timeout=1000)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])
        self.assertGreaterEqual(pg.probes, 3)

    def test_a_cache_hit_under_a_service_worker_is_not_a_failure(self):
        logs = []
        fail = ('requestfailed', _Req('https://helpmap.uk/data.js?v=1', failure='net::ERR_FAILED'))
        pg = _DelayedReady([[fail]], sw=True, ready_after=3)
        B.goto(pg, 'http://127.0.0.1/?nocount', log=logs.append, ready_timeout=1000)
        self.assertEqual(pg.gotos, 1)
        self.assertEqual(logs, [])

    def test_a_service_worker_cache_miss_is_still_a_failure(self):
        logs = []
        fail = ('requestfailed', _Req('https://helpmap.uk/data.js?v=1', failure='net::ERR_FAILED'))
        pg = _DelayedReady([[fail], [fail]], sw=True, stay_down=True)
        with self.assertRaises(B.AppNotReady):
            B.goto(pg, 'http://127.0.0.1/?nocount', log=logs.append, ready_timeout=400)
        self.assertEqual(pg.gotos, 2)
        self.assertEqual(len(logs), 1)
        self.assertIn('retry: script failed to load', logs[0])


class Wired(unittest.TestCase):
    def test_no_check_waits_for_networkidle(self):
        bad = []
        for rel in CHECK_FILES:
            text = open(os.path.join(R, rel), encoding='utf-8').read()
            if IDLE.search(text):
                bad.append(rel)
        self.assertEqual(bad, [])

    def test_live_checks_use_the_helper(self):
        for rel in ('scripts/journeys.py', 'scripts/design_lock.py', 'scripts/old_links.py', 'scripts/dark_default.py', 'scripts/sense_check.py'):
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
        self.assertIn('android', o)  # Instagram Android webview as well as iOS
        dflt = open(os.path.join(R, 'scripts', 'dark_default.py'), encoding='utf-8').read()
        self.assertIn('new_context', dflt)
        self.assertIn('B.goto', dflt)

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

    def test_no_check_requests_a_real_tile_host(self):
        """Rule 23. Fails if a check would open a tile host, or if new_context stops stubbing tiles."""
        import inspect
        self.assertNotIn('continue_', inspect.getsource(B.fulfill_tile))
        self.assertNotIn('fallback', inspect.getsource(B.fulfill_tile))
        self.assertIn('install_tile_stub(c)', inspect.getsource(B.new_context))
        class Route:
            def __init__(self):
                self.kw = None
            def fulfill(self, **kw):
                self.kw = kw
            def continue_(self, **kw):
                raise AssertionError('tile request continued to the network')
            def fallback(self, **kw):
                raise AssertionError('tile request fell through to the network')
        for url in (
            'https://tile.openstreetmap.org/0/0/0.png',
            'https://a.tile.openstreetmap.org/1/1/1.png',
            'https://api.maptiler.com/maps/streets-v2/256/0/0/0.png?key=abc',
            'https://tiles.stadiamaps.com/tiles/osm_bright/0/0/0.png',
        ):
            self.assertTrue(B.is_tile_host(url), url)
            route = Route()
            B.fulfill_tile(route)
            self.assertEqual(route.kw['status'], 200)
            self.assertEqual(route.kw['body'], B.PLACEHOLDER_PNG)
            self.assertIn('image/png', route.kw['content_type'])
        # The browser tests use a same-origin path that only looks like a tile. That is not a tile host.
        self.assertFalse(B.is_tile_host('http://127.0.0.1/tile.openstreetmap.org/5/15/9.png'))
        self.assertFalse(B.is_tile_host('https://helpmap.uk/icon-192.png'))
        self.assertTrue(B.PLACEHOLDER_PNG.startswith(b'\x89PNG\r\n\x1a\n'))
        scripts = os.path.join(R, 'scripts')
        for name in sorted(os.listdir(scripts)):
            if not name.endswith('.py'):
                continue
            text = open(os.path.join(scripts, name), encoding='utf-8').read()
            if 'sync_playwright' not in text and 'from playwright' not in text:
                continue
            if name == 'render_fetch.py':
                # Source-page render for opening times, not the map. It must not name a tile host.
                for host in B.TILE_HOSTS:
                    self.assertNotIn(host, text, name)
                continue
            if name == 'check_browser.py':
                continue
            self.assertIn('new_context', text, name)
            if '.launch(' in text:
                self.assertIn('B.launch(', text, name)
            # Sending the request on from a later route skips the placeholder tiles. fallback() does not.
            self.assertNotRegex(text, r'\.continue_\(', name)
            for host in B.TILE_HOSTS:
                self.assertNotRegex(text, r'''goto\(\s*['\"]https?://(?:[^/'\"]+\.)?%s''' % re.escape(host), name)


def _have_playwright():
    try:
        import playwright  # the plain test job has no browser; the browser job does
        return bool(playwright)
    except Exception:
        return False


@unittest.skipUnless(_have_playwright(), 'needs playwright')
class BlockRetry(unittest.TestCase):
    """Headless Chromium, cold context, tile-shaped responses answered on 127.0.0.1.
    Nothing is requested from a map tile host or from helpmap.uk."""

    def _run(self, mode, ready_timeout=700):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from playwright.sync_api import sync_playwright
        app = ('<!doctype html><html><head><title>Find a food bank, warm space or shelter near you</title></head>'
               '<body><input id="q"><div id="map"></div>'
               '<img src="/tile.openstreetmap.org/5/15/9.png" alt="">'
               '<script src="/data.js"></script>'
               '<script>var m=document.getElementById("map");if(window.FB_DATA)m.innerHTML="<div class=\\"leaflet-pane\\"></div>"</script>'
               '</body></html>')
        challenge = ('<!doctype html><html><head><title>Just a moment...</title></head>'
                     '<body>Checking your browser before accessing</body></html>')
        replaced = ('<!doctype html><html><head><title>Find a food bank, warm space or shelter near you – helpmap.uk</title></head>'
                    '<body><p>Find help near you</p></body></html>')
        ok_js = 'window.FB_DATA={items:new Array(201)};'
        bug_js = 'throw new Error("our bug");'

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
            def log_message(self, *a):
                pass

        httpd = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/?nocount' % httpd.server_address[1]
        docs, offbox, logs, scripts = [], [], [], []

        def handle(route):
            req = route.request
            host = req.url.split('/')[2]
            if not host.startswith('127.0.0.1'):
                offbox.append(req.url)
                route.fulfill(status=403, body='off box', content_type='text/plain')
                return
            if req.resource_type == 'document':
                docs.append(req.url)
                if mode == 'challenge-twice' or (mode == 'challenge-once' and len(docs) == 1):
                    route.fulfill(status=200, body=challenge, content_type='text/html')
                elif mode == 'replaced':
                    route.fulfill(status=200, body=replaced, content_type='text/html')
                else:
                    route.fulfill(status=200, body=app, content_type='text/html')
                return
            if 'tile.openstreetmap.org' in req.url:
                route.fulfill(status=403, body='', content_type='image/png')
                return
            if 'data.js' in req.url:
                scripts.append(req.url)
                if mode == 'script-403' or (mode == 'script-403-once' and len(scripts) == 1):
                    route.fulfill(status=403, body='no', content_type='text/javascript')
                elif mode == 'script-404':
                    route.fulfill(status=404, body='missing', content_type='text/javascript')
                elif mode == 'script-500':
                    route.fulfill(status=500, body='down', content_type='text/javascript')
                elif mode == 'script-bug':
                    route.fulfill(status=200, body=bug_js, content_type='text/javascript')
                else:
                    route.fulfill(status=200, body=ok_js, content_type='text/javascript')
                return
            route.fulfill(status=404, body='', content_type='text/plain')

        err = None
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()  # headless bundled Chromium
                context = B.new_context(browser, viewport={'width': 390, 'height': 700})
                context.route('**/*', handle)
                page = context.new_page()
                try:
                    B.goto(page, base, log=logs.append, ready_timeout=ready_timeout)
                except Exception as e:
                    err = e
                context.close()
                browser.close()
        finally:
            httpd.shutdown()
        self.assertEqual(offbox, [])
        return docs, logs, err, scripts

    def test_tile_hosts_do_not_resolve_and_a_worker_cannot_fetch_one(self):
        """Rule 23. The route serves a placeholder. A service worker, which the route cannot see, still cannot open a tile host."""
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from playwright.sync_api import sync_playwright
        html = b'<!doctype html><script>navigator.serviceWorker.register("/sw.js")</script>'
        sw = b'''self.addEventListener("install",e=>self.skipWaiting());
self.addEventListener("activate",e=>e.waitUntil(self.clients.claim()));
self.addEventListener("fetch",e=>{if(/openstreetmap|maptiler|stadiamaps/.test(e.request.url))e.respondWith(fetch(e.request));});
'''
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = sw if self.path.startswith('/sw.js') else html
                self.send_response(200)
                self.send_header('content-type', 'application/javascript' if body is sw else 'text/html')
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *a):
                pass
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d/' % httpd.server_address[1]
        try:
            with sync_playwright() as p:
                browser = B.launch(p.chromium)
                bare = browser.new_context()
                page = bare.new_page()
                for url in (
                    'https://tile.openstreetmap.org/0/0/0.png',
                    'https://a.tile.openstreetmap.org/1/0/0.png',
                    'https://api.maptiler.com/maps/streets-v2/256/0/0/0.png?key=abc',
                    'https://tiles.stadiamaps.com/tiles/osm_bright/0/0/0.png',
                ):
                    with self.assertRaises(Exception) as cm:
                        page.goto(url, wait_until='commit', timeout=5000)
                    self.assertIn('ERR_NAME_NOT_RESOLVED', str(cm.exception), url)
                bare.close()
                context = B.new_context(browser, service_workers='allow')
                pg = context.new_page()
                pg.goto(base)
                pg.wait_for_function('navigator.serviceWorker.controller', timeout=8000)
                got = pg.evaluate('''async()=>{try{const r=await fetch("https://tile.openstreetmap.org/3/1/1.png");
                  return "body "+(await r.arrayBuffer()).byteLength}catch(e){return "err "+String(e)}}''')
                self.assertFalse(str(got).startswith('body '), got)
                context.close()
                browser.close()
        finally:
            httpd.shutdown()

    def test_offline_context_serves_a_placeholder_for_every_tile_host(self):
        """The browser is offline. A real tile host is unreachable; the placeholder is the only answer."""
        from playwright.sync_api import sync_playwright
        urls = (
            'https://tile.openstreetmap.org/0/0/0.png',
            'https://a.tile.openstreetmap.org/1/0/0.png',
            'https://api.maptiler.com/maps/streets-v2/256/0/0/0.png?key=abc',
            'https://tiles.stadiamaps.com/tiles/osm_bright/0/0/0.png',
        )
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = B.new_context(browser, offline=True)
            page = context.new_page()
            try:
                for url in urls:
                    resp = page.goto(url, wait_until='commit', timeout=5000)
                    self.assertIsNotNone(resp, url)
                    self.assertEqual(resp.status, 200, url)
                    self.assertEqual(resp.body(), B.PLACEHOLDER_PNG, url)
                with self.assertRaises(Exception):
                    page.goto('https://example.com/', wait_until='commit', timeout=3000)
            finally:
                context.close()
                browser.close()

    def test_tile_403_and_a_ready_page_is_one_load(self):
        docs, logs, err, _ = self._run('ok')
        self.assertIsNone(err)
        self.assertEqual(len(docs), 1)
        self.assertEqual(logs, [])

    def test_boot_script_403_is_retried_once_and_then_passes(self):
        docs, logs, err, scripts = self._run('script-403-once')
        self.assertIsNone(err)
        self.assertEqual(len(docs), 2)
        self.assertEqual(len(scripts), 2)
        self.assertEqual(len(logs), 1)
        self.assertIn('blocked or challenged', logs[0])

    def test_boot_script_403_twice_is_a_failure(self):
        docs, logs, err, _ = self._run('script-403')
        self.assertIsInstance(err, B.BlockedPage)
        self.assertIn('n', str(err))
        self.assertEqual(len(docs), 2)
        self.assertEqual(len(logs), 1)

    def test_missing_boot_script_is_a_real_failure_with_no_retry(self):
        docs, logs, err, _ = self._run('script-404')
        self.assertIsInstance(err, B.AppNotReady)
        self.assertIn("'n': 0", str(err))
        self.assertIn('pane', str(err))
        self.assertEqual(len(docs), 1)
        self.assertEqual(logs, [])

    def test_boot_script_500_is_a_real_failure_with_no_retry(self):
        docs, logs, err, _ = self._run('script-500')
        self.assertIsInstance(err, B.AppNotReady)
        self.assertIn("'n': 0", str(err))
        self.assertEqual(len(docs), 1)
        self.assertEqual(logs, [])

    def test_our_script_throwing_is_a_real_failure_even_when_a_tile_403s(self):
        docs, logs, err, _ = self._run('script-bug')
        self.assertIsInstance(err, B.AppNotReady)
        self.assertEqual(len(docs), 1)
        self.assertEqual(logs, [])

    def test_challenge_then_the_app_passes_and_a_second_challenge_fails(self):
        docs, logs, err, _ = self._run('challenge-once')
        self.assertIsNone(err)
        self.assertEqual(len(docs), 2)
        self.assertEqual(len(logs), 1)
        docs, logs, err, _ = self._run('challenge-twice')
        self.assertIsInstance(err, B.BotPage)
        self.assertEqual(len(docs), 2)

    def test_titled_block_page_is_retried_then_fails(self):
        docs, logs, err, _ = self._run('replaced')
        self.assertIsInstance(err, B.BlockedPage)
        self.assertIn('pane', str(err))
        self.assertEqual(len(docs), 2)
        self.assertEqual(len(logs), 1)
