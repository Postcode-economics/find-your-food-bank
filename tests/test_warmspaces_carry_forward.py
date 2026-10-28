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
        items, carried, _ = C.carry_items([SAIFEE, KINGS, OTHER], [dict(OTHER)], [], '2026-10-28', allowed=set())
        by = {x['id']: x for x in items}
        self.assertEqual(set(by), {SAIFEE['id'], KINGS['id'], OTHER['id']})
        for k in (SAIFEE['id'], KINGS['id']):
            self.assertTrue(by[k]['call_check']); self.assertEqual(by[k]['carried_forward'], '2026-10-28')
            self.assertFalse(by[k]['stale'])
        self.assertEqual(by[SAIFEE['id']]['phone'], SAIFEE['phone']); self.assertEqual(by[SAIFEE['id']]['postcode'], 'B18 6PU')
        self.assertNotIn('call_check', by[OTHER['id']])
        self.assertEqual({x['id'] for x in carried}, {SAIFEE['id'], KINGS['id']})

    def test_carried_since_kept_across_runs(self):
        first, _, _ = C.carry_items([SAIFEE], [], [], '2026-10-28', allowed=set())
        second, _, _ = C.carry_items(first, [], [], '2026-11-20', allowed=set())
        self.assertEqual(second[0]['carried_since'], '2026-10-28'); self.assertEqual(second[0]['carried_forward'], '2026-11-20')
        self.assertTrue(second[0]['call_check'])

    def test_only_deliberate_removals_skipped(self):
        closed = [dict(KINGS, flag_closed=True, closed_on='2026-10-28')]
        items, carried, _ = C.carry_items([SAIFEE, KINGS, OTHER], [], closed, '2026-10-28', excluded={OTHER['id']}, allowed=set())
        self.assertEqual([x['id'] for x in items], [SAIFEE['id']])
        items, _, _ = C.carry_items([SAIFEE], [], [], '2026-10-28', allowed={SAIFEE['id']})
        self.assertEqual(items, [])

    def test_review_log_written(self):
        d = tempfile.mkdtemp()
        try:
            _, carried, _ = C.carry_items([SAIFEE], [], [], '2026-10-28', allowed=set())
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
        self.assertIn('valid_until=season_end', s); self.assertIn('pending=PENDING', s)
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

def season_end(v):  # same rule as build_warmspaces.season_end
    import datetime
    d = datetime.date.fromisoformat(v.get("verified_on", "2000-01-01"))
    return f"{d.year + (1 if d.month >= 9 else 0)}-04-30"

class Rework(unittest.TestCase):
    """GB2 FAIL on 02228cf28: label not delete, flag after 14 days, respect season, skip deliberate removals, moved ids, redirects."""
    def test_note_shows_carried_since(self):
        items, carried, _ = C.carry_items([SAIFEE], [], [], '2026-10-28', allowed=set())
        self.assertEqual(carried[0]['carried_note'], 'Not re-confirmed since 2026-10-28 – call before you go')
        later, c2, _ = C.carry_items(items, [], [], '2026-11-05', allowed=set())
        self.assertEqual(c2[0]['carried_note'], 'Not re-confirmed since 2026-10-28 – call before you go')

    def test_flagged_for_review_after_14_days_never_deleted(self):
        first, _, _ = C.carry_items([SAIFEE], [], [], '2026-10-28', allowed=set())
        _, c13, _ = C.carry_items(first, [], [], '2026-11-10', allowed=set())
        self.assertFalse(c13[0]['review'])
        _, c14, _ = C.carry_items(first, [], [], '2026-11-11', allowed=set())
        self.assertTrue(c14[0]['review']); self.assertEqual(c14[0]['carried_days'], 14)
        far, cfar, _ = C.carry_items(first, [], [], '2027-03-01', allowed=set(), valid_until=season_end)
        self.assertEqual([x['id'] for x in far], [SAIFEE['id']])  # still published inside the season, labelled
        d = tempfile.mkdtemp()
        try:
            C.write_log(c14, '2026-11-11', root=d)
            lg = json.load(open(os.path.join(d, 'logs', 'warmspaces_carry_forward.json')))
            self.assertTrue(lg['carried'][0]['review'])
            md = open(os.path.join(d, 'reports', 'warmspaces_carry_forward.md')).read()
            self.assertIn('## For review', md); self.assertIn('Saifee Mosque', md.split('## Carried')[0])
        finally: shutil.rmtree(d)

    def test_season_end_respected(self):
        items, carried, nc = C.carry_items([SAIFEE], [], [], '2027-05-01', allowed=set(), valid_until=season_end)
        self.assertEqual(items, []); self.assertEqual(nc[0]['why'], 'season_ended')
        old = dict(SAIFEE, scheme_end='2026-10-20')
        items, _, nc = C.carry_items([old], [], [], '2026-10-28', allowed=set(), valid_until=season_end)
        self.assertEqual(items, []); self.assertEqual(nc[0]['why'], 'season_ended')
        items, _, _ = C.carry_items([dict(SAIFEE, ended=True)], [], [], '2026-10-28', allowed=set())
        self.assertEqual(items, [])

    def test_deliberate_removals_not_carried(self):
        _, _, nc = C.carry_items([SAIFEE, KINGS, OTHER], [], [], '2026-10-28', excluded={SAIFEE['id']}, allowed={KINGS['id']}, skip={OTHER['id']})
        self.assertEqual({r['id']: r['why'] for r in nc}, {SAIFEE['id']: 'excluded', KINGS['id']: 'guard_allow_remove', OTHER['id']: 'closed'})
        items, _, nc = C.carry_items([dict(SAIFEE, flag_closed=True)], [], [], '2026-10-28', allowed=set())
        self.assertEqual(items, []); self.assertEqual(nc[0]['why'], 'closed')

    def test_redirect_drops_link_keeps_venue_flagged(self):
        kings = dict(KINGS, website='https://kingschurchhx.org.uk/')
        pend = [{'id': KINGS['id'], 'reason': 'omitted this run: source URL now redirects to a different site',
                 'recheck': {'url': 'https://kingschurchhx.org.uk/', 'final_url': 'https://cornerstonechurchhalifax.co.uk/'}}]
        items, carried, _ = C.carry_items([kings], [], [], '2026-10-28', allowed=set(), pending=pend)
        x = items[0]
        self.assertNotIn('website', x); self.assertEqual(x['website_redirects_to'], 'cornerstonechurchhalifax.co.uk')
        self.assertTrue(x['review']); self.assertTrue(x['call_check'])
        same = [{'id': KINGS['id'], 'recheck': {'url': 'https://kingschurchhx.org.uk/', 'final_url': 'https://www.kingschurchhx.org.uk/x'}}]
        items, _, _ = C.carry_items([kings], [], [], '2026-10-28', allowed=set(), pending=same)
        self.assertEqual(items[0]['website'], 'https://kingschurchhx.org.uk/')

    def test_moved_venue_not_listed_twice(self):
        rekeyed = dict(SAIFEE, id='ww-999', lat=52.4901)
        items, carried, nc = C.carry_items([SAIFEE], [rekeyed], [], '2026-10-28', allowed=set())
        self.assertEqual([x['id'] for x in items], ['ww-999']); self.assertEqual(carried, [])
        self.assertEqual(nc[0]['why'], 'moved_to:ww-999')
        far = dict(SAIFEE, id='ww-998', lat=55.0, lng=-3.0, postcode='DG1 1AA')
        items, _, _ = C.carry_items([SAIFEE], [far], [], '2026-10-28', allowed=set())
        self.assertEqual(len(items), 2)  # same name far away is a different place

    def test_guard_uses_shared_moved_matcher(self):
        out, rep = G.guard('warmspaces', [SAIFEE], [dict(SAIFEE, id='ww-999')])
        self.assertEqual(rep['places'], []); self.assertEqual([x['id'] for x in out], ['ww-999'])

    def test_area_card_and_map_show_note(self):
        import build_seo as B
        _, c, _ = C.carry_items([dict(SAIFEE, address='a')], [], [], '2026-10-28', allowed=set())
        self.assertIn('Not re-confirmed since 2026-10-28 – call before you go', B.card_ws(c[0]))
        v3 = open(os.path.join(ROOT, 'v3.js'), encoding='utf-8').read()
        self.assertIn('Not re-confirmed since ${esc3(i.carried_since)} – call before you go', v3)

class AreaPagesRework(unittest.TestCase):
    def _build(self, page):
        import build_seo as B
        d = tempfile.mkdtemp()
        for f in ('data.full.js', 'access.js', 'warmspaces.js', 'shelters.js'):
            shutil.copy(os.path.join(ROOT, f), d)
        os.makedirs(os.path.join(d, 'warm-spaces', 'zz-gone-area'))
        open(os.path.join(d, 'warm-spaces', 'zz-gone-area', 'index.html'), 'w').write(page)
        for x in ('food-banks', 'shelters'): os.makedirs(os.path.join(d, x), exist_ok=True)
        cwd = os.getcwd(); os.chdir(d)
        try: B.build(out=d, fetch=False)
        finally: os.chdir(cwd)
        return d, B.build.ws_area_kept

    def test_kept_page_note_and_since_preserved(self):
        import datetime
        d, kept = self._build('<html><div class="call">Always call before you go</div>Old Hub</html>')
        try:
            t = open(os.path.join(d, 'warm-spaces', 'zz-gone-area', 'index.html')).read()
            today = datetime.date.today().isoformat()
            self.assertIn('Not re-confirmed since %s – call before you go.' % today, t)
            k = next(k for k in kept if k['area'] == 'zz-gone-area'); self.assertFalse(k['review'])
        finally: shutil.rmtree(d)

    def test_kept_page_flagged_after_14_days_not_deleted(self):
        d, kept = self._build('<html><div class="call carried" data-since="2026-01-01">Not re-confirmed since 2026-01-01 – call before you go.</div><div class="call">x</div>Old Hub</html>')
        try:
            t = open(os.path.join(d, 'warm-spaces', 'zz-gone-area', 'index.html')).read()
            self.assertIn('Old Hub', t); self.assertEqual(t.count('class="call carried"'), 1)
            k = next(k for k in kept if k['area'] == 'zz-gone-area')
            self.assertEqual(k['carried_since'], '2026-01-01'); self.assertTrue(k['review'])
        finally: shutil.rmtree(d)

if __name__ == '__main__': unittest.main()
