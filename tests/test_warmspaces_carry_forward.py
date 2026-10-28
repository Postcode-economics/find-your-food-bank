"""Dean 28 Oct 2026: remove nothing. A warm space missing from this run's feed is carried forward, labelled
'call before you go' (call_check) and logged for review; warm-space area pages are never deleted."""
import json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import carry_forward as C
import refresh_guard as G
ROOT = os.path.join(os.path.dirname(__file__), '..')

SAIFEE = {'id': 'oi-birmingham-council-saifee-mosque-b18-6pu', 'name': 'Saifee Mosque', 'postcode': 'B18 6PU', 'lat': 52.49, 'lng': -1.92,
          'phone': '0121 000 0000', 'hours': {'Sat': '10:00 - 14:00'}, 'last_verified': '2026-10-27', 'tier': 'unverified', 'stale': False}
KINGS = {'id': 'ww-65441920', 'name': "The King's Church Halifax", 'postcode': 'HX1 2TS', 'lat': 53.72, 'lng': -1.86,
         'hours': {'Wed': '10:00 - 12:00'}, 'last_verified': '2026-10-26', 'tier': 'unverified', 'stale': False}
OTHER = {'id': 'ww-1', 'name': 'Other Hub', 'postcode': 'N3 1TR', 'lat': 51.6, 'lng': -0.19, 'hours': {}, 'last_verified': '2026-10-28', 'stale': False}

class CarryForward(unittest.TestCase):
    def test_feed_missing_venue_still_output_labelled(self):
        items, carried = C.carry_items([SAIFEE, KINGS, OTHER], [dict(OTHER)], [], '2026-10-28', allowed=set())
        by = {x['id']: x for x in items}
        self.assertEqual(set(by), {SAIFEE['id'], KINGS['id'], OTHER['id']})
        for k in (SAIFEE['id'], KINGS['id']):
            self.assertTrue(by[k]['call_check']); self.assertEqual(by[k]['carried_forward'], '2026-10-28')
            self.assertFalse(by[k]['stale'])
        self.assertEqual(by[SAIFEE['id']]['phone'], SAIFEE['phone']); self.assertEqual(by[SAIFEE['id']]['postcode'], 'B18 6PU')
        self.assertNotIn('call_check', by[OTHER['id']])
        self.assertEqual({x['id'] for x in carried}, {SAIFEE['id'], KINGS['id']})

    def test_carried_since_kept_across_runs(self):
        first, _ = C.carry_items([SAIFEE], [], [], '2026-10-28', allowed=set())
        second, _ = C.carry_items(first, [], [], '2026-11-20', allowed=set())
        self.assertEqual(second[0]['carried_since'], '2026-10-28'); self.assertEqual(second[0]['carried_forward'], '2026-11-20')
        self.assertTrue(second[0]['call_check'])

    def test_only_deliberate_removals_skipped(self):
        closed = [dict(KINGS, flag_closed=True, closed_on='2026-10-28')]
        items, carried = C.carry_items([SAIFEE, KINGS, OTHER], [], closed, '2026-10-28', excluded={OTHER['id']}, allowed=set())
        self.assertEqual([x['id'] for x in items], [SAIFEE['id']])
        items, _ = C.carry_items([SAIFEE], [], [], '2026-10-28', allowed={SAIFEE['id']})
        self.assertEqual(items, [])

    def test_review_log_written(self):
        d = tempfile.mkdtemp()
        try:
            _, carried = C.carry_items([SAIFEE], [], [], '2026-10-28', allowed=set())
            C.write_log(carried, '2026-10-28', root=d)
            lg = json.load(open(os.path.join(d, 'logs', 'warmspaces_carry_forward.json')))
            self.assertEqual(lg['carried'][0]['id'], SAIFEE['id'])
            self.assertIn('Saifee Mosque', open(os.path.join(d, 'reports', 'warmspaces_carry_forward.md')).read())
        finally: shutil.rmtree(d)

    def test_refresh_guard_labels_restored_warm_space(self):
        out, rep = G.guard('warmspaces', [SAIFEE, OTHER], [dict(OTHER)])
        self.assertEqual(rep['places'], [SAIFEE['id']])
        self.assertTrue(next(x for x in out if x['id'] == SAIFEE['id'])['call_check'])

    def test_build_wires_carry_forward(self):
        s = open(os.path.join(ROOT, 'scripts', 'build_warmspaces.py')).read()
        self.assertIn('carry_forward.carry_items(PREV_ITEMS, items, closed, RUN', s)
        self.assertLess(s.index('carry_forward.carry_items'), s.index('write_js(OUT'))

class AreaPages(unittest.TestCase):
    def test_carried_venue_counts_for_area_pages(self):
        import build_seo as B
        self.assertIn('call before you go', B.card_ws(dict(SAIFEE, call_check=True, stale=True, address='a')))

    def test_warm_space_area_page_never_deleted(self):
        import build_seo as B
        d = tempfile.mkdtemp()
        try:
            for f in ('data.full.js', 'access.js', 'warmspaces.js', 'shelters.js'):
                shutil.copy(os.path.join(ROOT, f), d)
            os.makedirs(os.path.join(d, 'warm-spaces', 'zz-gone-area'))
            open(os.path.join(d, 'warm-spaces', 'zz-gone-area', 'index.html'), 'w').write('<html><div class="call">Always call before you go</div>Old Hub</html>')
            for x in ('food-banks', 'shelters'): os.makedirs(os.path.join(d, x), exist_ok=True)
            cwd = os.getcwd(); os.chdir(d)
            try: B.build(out=d, fetch=False)
            finally: os.chdir(cwd)
            p = os.path.join(d, 'warm-spaces', 'zz-gone-area', 'index.html')
            self.assertTrue(os.path.exists(p)); t = open(p).read()
            self.assertIn('Old Hub', t); self.assertIn('class="call carried"', t)
            self.assertIn('/warm-spaces/zz-gone-area/', open(os.path.join(d, 'sitemap.xml')).read())
        finally: shutil.rmtree(d)

if __name__ == '__main__': unittest.main()
