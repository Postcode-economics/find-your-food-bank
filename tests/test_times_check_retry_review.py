"""Own-site times check (27 Oct 2026): polite slow retry on 403/429, late pass for centres added after the main
check, and a manual-review list that never invents times.

The card sentence in index.html is left unchanged: this piece does not edit map or front-end files.
The review list still records 'Opening times not known, call before you go' for a card with no published times.
"""
import os, sys, json, re, csv, inspect, tempfile, unittest, urllib.error, email.message
ROOT = os.path.join(os.path.dirname(__file__), '..'); sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import discover as D


class Resp:
    def __init__(self, url, body='<html>ok</html>'):
        self.status, self._u, self._b = 200, url, body.encode(); self.headers = email.message.Message()
    def read(self, n=-1): return self._b
    def geturl(self): return self._u


def http_error(url, code, retry_after=None):
    h = email.message.Message()
    if retry_after is not None: h['Retry-After'] = str(retry_after)
    return urllib.error.HTTPError(url, code, 'refused', h, None)


class RetryTest(unittest.TestCase):
    def setUp(self):
        self.o_open, self.o_sleep = D._open, D._sleep
        self.sleeps, self.calls = [], []
        D._sleep = self.sleeps.append; D._cache.clear()
    def tearDown(self):
        D._open, D._sleep = self.o_open, self.o_sleep; D._cache.clear()
    def script(self, outcomes):
        it = iter(outcomes)
        def op(url, headers):
            self.calls.append(headers['User-Agent']); x = next(it)
            if isinstance(x, Exception): raise x
            return x
        D._open = op

    def test_429_then_ok_retries_slowly_with_polite_ua(self):
        u = 'https://a.example/'
        self.script([http_error(u, 429), http_error(u, 403), Resp(u)])
        r = D.fetch_raw(u)
        self.assertEqual(r['http'], 200); self.assertEqual(r['retries'], 2)
        self.assertEqual(self.sleeps, [D.RETRY_BASE, D.RETRY_BASE * 3])       # backoff grows
        self.assertEqual(self.calls[0], D.UA['User-Agent'])
        self.assertTrue(all(c == D.POLITE_UA['User-Agent'] for c in self.calls[1:]))
        self.assertIn('helpmap.uk', D.POLITE_UA['User-Agent'])
        self.assertIn('HelpMapBot/1.0', D.POLITE_UA['User-Agent'])

    def test_gives_up_after_limit_and_reports_code(self):
        u = 'https://b.example/'
        self.script([http_error(u, 403)] * (D.RETRY_TRIES + 1))
        r = D.fetch_raw(u)
        self.assertEqual(r['http'], 403); self.assertEqual(r['retries'], D.RETRY_TRIES)
        self.assertEqual(len(self.calls), D.RETRY_TRIES + 1)

    def test_404_and_errors_are_not_retried(self):
        u = 'https://c.example/'
        self.script([http_error(u, 404)])
        self.assertEqual(D.fetch_raw(u)['http'], 404); self.assertEqual(self.sleeps, [])

    def test_retry_after_honoured_but_capped(self):
        self.assertEqual(D.retry_delay(1, '20'), 20)
        self.assertEqual(D.retry_delay(1, '9999'), D.RETRY_AFTER_CAP)
        self.assertEqual(D.retry_delay(2, 'Wed, 21 Oct 2026 07:28:00 GMT'), D.RETRY_BASE * 3)


def page(body):
    return {'http': 200, 'final_url': 'https://fb.example/', 'html': body, 'sha256': 'x', 'etag': '', 'last_modified': ''}


class LatePassTest(unittest.TestCase):
    def test_missing_centres_are_checked_and_manual_times_never_overwritten(self):
        ot = {'status': 'TIMES_FOUND', 'structured': {'tue': [['10:00', '12:00']]}, 'raw': 'Tuesday 10am - 12pm', 'checked_date': '2026-10-21'}
        items = [{'id': 'fb', 'type': 'foodbank', 'website': 'https://fb.example/', 'opening_times': dict(ot)},
                 {'id': 'fb/centre', 'type': 'location', 'manual': True, 'website': 'https://fb.example/', 'opening_times': dict(ot)},
                 {'id': 'fb/other', 'type': 'location', 'manual': True, 'website': 'https://fb.example/',
                  'opening_times': {'status': 'TIMES_FOUND', 'structured': {'fri': [['13:00', '15:00']]}, 'raw': 'Friday 1pm - 3pm'}}]
        f = lambda u: page('<p>Open Tuesday 10am - 12pm at our hall.</p>')
        log = {'fb': {'status': 'confirmed'}}
        late = D.check_missing(items, log, 'fb', 'opening_times', fetcher=f)
        self.assertEqual(sorted(late), ['fb/centre', 'fb/other'])
        self.assertTrue(all(log[k].get('late_pass') for k in late))
        self.assertEqual(log['fb/centre']['status'], 'confirmed')
        self.assertTrue(items[1]['opening_times']['checked_date'] > '2026-10-21')   # card date advances
        self.assertEqual(items[2]['opening_times']['structured'], {'fri': [['13:00', '15:00']]})  # hand-checked kept
        self.assertNotEqual(log['fb/other']['status'], 'changed')

    def test_build_runs_late_pass_and_writes_review_to_logs(self):
        b = open(os.path.join(ROOT, 'scripts', 'build.py')).read()
        self.assertIn('discover.check_missing(items, tlog', b)
        self.assertLess(b.index('check_missing'), b.index("meta = schema_version.stamp(dict(fetched"))
        self.assertIs(inspect.signature(D.check_missing).parameters['fetcher'].default, D.fetch_live)
        self.assertIn("'logs', 'foodbank_times_review.csv'", b)
        self.assertIn('state_root=ROOT', b)
        wf = open(os.path.join(ROOT, '.github', 'workflows', 'refresh.yml')).read()
        self.assertIn('logs/foodbank_times_review.csv', wf); self.assertIn('logs/foodbank_times_review.json', wf)
        self.assertIn('logs/times_crosscheck_seen.json', wf)
        for name in ('refresh-shelters.yml', 'refresh-warmspaces.yml'):
            text = open(os.path.join(ROOT, '.github', 'workflows', name)).read()
            self.assertIn('logs/times_crosscheck_seen.json', text, name)
            self.assertIn('reports/times_auto_applied.json', text, name)


class ReviewTest(unittest.TestCase):
    def test_categories_and_no_invented_times(self):
        items = [{'id': 'a', 'name': 'A', 'opening_times': {'status': 'TIMES_FOUND', 'structured': {'mon': [['9:00', '10:00']]}}},
                 {'id': 'b', 'name': 'B', 'opening_times': None}, {'id': 'c', 'name': 'C'}, {'id': 'd', 'name': 'D'},
                 {'id': 'e', 'name': 'E'}, {'id': 'f', 'name': 'F'}]
        log = {'a': {'status': 'unconfirmed', 'reason': 'published times not found on own site this run', 'http': 200, 'site': 'https://a/'},
               'b': {'status': 'none_published', 'reason': 'no times published or found', 'http': 200},
               'c': {'status': 'unconfirmed', 'reason': 'own site redirects to a different site', 'final_url': 'https://other/'},
               'd': {'status': 'no_website', 'reason': 'no own website to check against'},
               'e': {'status': 'unreachable', 'http': 429, 'retries': 3, 'reason': 'own site unreachable this run'},
               'f': {'status': 'confirmed', 'reason': 'ok'}}
        rows = {r['id']: r for r in D.times_review(log, items)}
        self.assertEqual({k: r['category'] for k, r in rows.items()},
                         {'a': 'times_not_found', 'b': 'times_not_found', 'c': 'redirected', 'd': 'no_source', 'e': 'blocked_after_retries'})
        self.assertEqual(rows['c']['final_url'], 'https://other/')
        self.assertEqual(rows['a']['card_shows'], 'times kept from the main listing')
        self.assertEqual(rows['b']['card_shows'], 'Opening times not known, call before you go')
        for r in rows.values():                      # the list carries no times of its own
            self.assertFalse(any(re.search(r'\d{1,2}:\d{2}', str(v)) for v in r.values()))
        with tempfile.TemporaryDirectory() as t:
            D.write_review(list(rows.values()), os.path.join(t, 'r.csv'), os.path.join(t, 'r.json'))
            self.assertEqual(len(list(csv.DictReader(open(os.path.join(t, 'r.csv'))))), 5)
            j = json.load(open(os.path.join(t, 'r.json')))
            self.assertEqual(j['counts']['times_not_found'], 2)


if __name__ == '__main__': unittest.main()
