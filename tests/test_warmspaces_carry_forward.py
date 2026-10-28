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

OLD_HUB = {'id': 'ww-old-hub', 'name': 'Old Hub', 'postcode': 'ZZ9 9ZZ', 'lat': 51.0, 'lng': 0.5, 'address': '1 Old Road',
           'hours': {'Wed': '10:00 - 12:00'}, 'verified_on': '2026-10-20', 'last_verified': '2026-10-20', 'stale': False}
OLD_PAGE = '<html><h1>Warm spaces in Gone Area</h1>%s<div class="call">Always call before you go</div><ul class="s"><li><div class="n">Old Hub</div></li></ul></html>'

def build_with(page, extra_ws, env=None):
    """build_seo into a temp dir with a previous warm-spaces/zz-gone-area page and `extra_ws` added to warmspaces.js.
    ZZ9 9ZZ has no area in the district cache, so only the previous page ties Old Hub to zz-gone-area."""
    import build_seo as B
    from unittest import mock
    real = B.load_js
    def load_js(name, var):
        o = real(name, var)
        if name == 'warmspaces.js': o['items'] = o['items'] + [dict(x) for x in extra_ws]
        return o
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, 'warm-spaces', 'zz-gone-area'))
    open(os.path.join(d, 'warm-spaces', 'zz-gone-area', 'index.html'), 'w').write(page)
    for x in ('food-banks', 'shelters'): os.makedirs(os.path.join(d, x), exist_ok=True)
    with mock.patch.object(B, 'load_js', load_js), mock.patch.dict(os.environ, env or {}):
        if not env: os.environ.pop('PRIVATE_BLOCKLIST', None)
        B.build(out=d, fetch=False)
    return d, B.build.ws_area_kept

def carried(o, run='2026-10-28', **kw):
    return C.carry_items([o], [], [], run, allowed=set(), **kw)[0]

class AreaPages(unittest.TestCase):
    def test_carried_venue_counts_for_area_pages(self):
        import build_seo as B
        self.assertIn('call before you go', B.card_ws(dict(SAIFEE, call_check=True, stale=True, address='a')))

    def test_warm_space_area_page_never_deleted(self):
        d, _ = build_with(OLD_PAGE % '', carried(OLD_HUB))
        try:
            p = os.path.join(d, 'warm-spaces', 'zz-gone-area', 'index.html')
            self.assertTrue(os.path.exists(p)); t = open(p).read()
            self.assertIn('Old Hub', t); self.assertIn('class="call carried"', t)
            self.assertIn('Not re-confirmed since 2026-10-20 – call before you go', t)   # rebuilt from the carried item's card
            self.assertIn('<h1>Warm spaces in Gone Area</h1>', t)
            self.assertIn('/warm-spaces/zz-gone-area/', open(os.path.join(d, 'sitemap.xml')).read())
        finally: shutil.rmtree(d)

    def _gone(self, d, kept, secret=None):
        self.assertFalse(os.path.exists(os.path.join(d, 'warm-spaces', 'zz-gone-area')))
        self.assertNotIn('/warm-spaces/zz-gone-area/', open(os.path.join(d, 'sitemap.xml')).read())
        self.assertNotIn('zz-gone-area', [k['area'] for k in kept])
        for top, _, files in os.walk(os.path.join(d, 'warm-spaces')):
            for f in files:
                t = open(os.path.join(top, f), encoding='utf-8').read()
                self.assertNotIn('Old Hub', t, f)
                if secret: self.assertNotIn(secret, t, f)

    def test_excluded_sole_venue_takes_its_area_page_with_it(self):
        """Review 28 Oct: a kept area page was copied forward as HTML, so a venue Dean excluded that was the only one in
        its area stayed published. carry_forward does not carry it; with no carried venue left the page goes."""
        items = carried(OLD_HUB, excluded={OLD_HUB['id']})
        self.assertEqual(items, [])
        d, kept = build_with(OLD_PAGE % '', items)
        try: self._gone(d, kept)
        finally: shutil.rmtree(d)

    def test_blocklisted_sole_venue_takes_its_area_page_with_it(self):
        addr = '99 Dummy Lane, Exampletown EX1 1EX'
        d, kept = build_with(OLD_PAGE % '', carried(dict(OLD_HUB, address=addr)), env={'PRIVATE_BLOCKLIST': addr})
        try: self._gone(d, kept, secret='99 Dummy Lane')
        finally: shutil.rmtree(d)

    def test_closed_or_ended_sole_venue_takes_its_area_page_with_it(self):
        for items in (carried(dict(OLD_HUB, flag_closed=True)), [dict(x, ended=True) for x in carried(OLD_HUB)]):
            d, kept = build_with(OLD_PAGE % '', items)
            try: self._gone(d, kept)
            finally: shutil.rmtree(d)

    def test_page_with_no_carried_venue_is_not_copied_forward(self):
        d, kept = build_with(OLD_PAGE % '', [dict(OLD_HUB)])   # in the file but not carried (no call_check)
        try: self._gone(d, kept)
        finally: shutil.rmtree(d)

def season_end(v):  # same rule as build_warmspaces.season_end
    import datetime
    d = datetime.date.fromisoformat(v.get("verified_on", "2000-01-01"))
    return f"{d.year + (1 if d.month >= 9 else 0)}-04-30"

class Rework(unittest.TestCase):
    """GB2 FAIL on 02228cf28: label not delete, flag after 14 days, respect season, skip deliberate removals, moved ids, redirects."""
    def test_note_shows_last_confirmed_date(self):  # GB2 on 089afe044: the date is the last confirmation, not the day carrying began
        items, carried, _ = C.carry_items([SAIFEE], [], [], '2026-10-28', allowed=set())
        self.assertEqual(carried[0]['carried_note'], 'Not re-confirmed since 2026-10-27 – call before you go')
        self.assertEqual(carried[0]['carried_since'], '2026-10-28'); self.assertEqual(carried[0]['last_confirmed'], '2026-10-27')
        later, c2, _ = C.carry_items(items, [], [], '2026-11-05', allowed=set())
        self.assertEqual(c2[0]['carried_note'], 'Not re-confirmed since 2026-10-27 – call before you go')
        _, c3, _ = C.carry_items([SAIFEE], [], [], '2026-10-28', allowed=set(), confirmed={SAIFEE['id']: '2026-10-25T21:30:43+00:00'})
        self.assertEqual(c3[0]['carried_note'], 'Not re-confirmed since 2026-10-25 – call before you go')
        nodate = {k: v for k, v in SAIFEE.items() if k != 'last_verified'}
        _, c4, _ = C.carry_items([nodate], [], [], '2026-10-28', allowed=set())
        self.assertEqual(c4[0]['carried_note'], 'Not re-confirmed since 2026-10-28 – call before you go')  # unknown: falls back to carried_since

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
        self.assertIn('Not re-confirmed since 2026-10-27 – call before you go', B.card_ws(c[0]))
        v3 = open(os.path.join(ROOT, 'v3.js'), encoding='utf-8').read()
        self.assertIn('const cd=esc3(i.last_confirmed||i.carried_since)', v3)
        self.assertIn('Not re-confirmed since ${cd} – call before you go', v3)

class AreaPagesRework(unittest.TestCase):
    def _build(self, page):
        return build_with(page, carried(OLD_HUB))

    def test_kept_page_note_and_since_preserved(self):
        import datetime
        d, kept = self._build(OLD_PAGE % '')
        try:
            t = open(os.path.join(d, 'warm-spaces', 'zz-gone-area', 'index.html')).read()
            today = datetime.date.today().isoformat()
            self.assertIn('Not re-confirmed since %s – call before you go.' % today, t)
            k = next(k for k in kept if k['area'] == 'zz-gone-area'); self.assertFalse(k['review'])
        finally: shutil.rmtree(d)

    def test_kept_page_flagged_after_14_days_not_deleted(self):
        d, kept = self._build(OLD_PAGE % '<div class="call carried" data-since="2026-01-01">Not re-confirmed since 2026-01-01 – call before you go.</div>')
        try:
            t = open(os.path.join(d, 'warm-spaces', 'zz-gone-area', 'index.html')).read()
            self.assertIn('Old Hub', t); self.assertEqual(t.count('class="call carried"'), 1)
            k = next(k for k in kept if k['area'] == 'zz-gone-area')
            self.assertEqual(k['carried_since'], '2026-01-01'); self.assertTrue(k['review'])
        finally: shutil.rmtree(d)

class GuardHonoursBuild(unittest.TestCase):
    """GB2 FAIL on 089afe044: refresh_guard (runs after the build) restored warm spaces the build left out on purpose,
    without the note and with the redirecting link. Simulates the workflow order (build carry-forward -> refresh_guard)."""
    def setUp(self):
        self.d = tempfile.mkdtemp(); os.makedirs(os.path.join(self.d, 'logs')); os.makedirs(os.path.join(self.d, 'overrides'))
        self.kings = dict(KINGS, website='https://kingschurchhx.org.uk/', verified_on='2026-10-20')
        self.excl = dict(OTHER, id='ww-excl', name='Excluded Hall', postcode='E1 1AA', lat=51.5, lng=-0.07, verified_on='2026-11-01', last_verified='2027-02-20')
        self.closed = dict(OTHER, id='ww-closed', name='Closed Hall', postcode='E2 2AA', lat=51.53, lng=-0.06, verified_on='2026-11-01', last_verified='2027-02-20')
        self.flagged = dict(OTHER, id='ww-flagged', name='Flagged Hall', postcode='E3 3AA', lat=51.52, lng=-0.03, verified_on='2026-11-01', last_verified='2027-02-20', flag_closed=True)
        self.alive = dict(OTHER, id='ww-alive', name='Spring Hub', postcode='E4 4AA', lat=51.6, lng=0.0,
                          verified_on='2026-11-20', last_verified='2027-02-20', website='https://springhub.org.uk/')
        self.keep = dict(OTHER, id='ww-keep', name='Keep Hub', postcode='E5 5AA', lat=51.55, lng=-0.05, verified_on='2026-11-01', last_verified='2027-02-20')
        json.dump([{'id': 'ww-excl', 'name': 'Excluded Hall', 'reason': 'test'}], open(os.path.join(self.d, 'overrides', 'warmspaces_exclude.json'), 'w'))
        json.dump([{'id': 'ww-alive', 'recheck': {'url': 'https://springhub.org.uk/', 'final_url': 'https://elsewhere.example/'}}],
                  open(os.path.join(self.d, 'logs', 'warmspaces_pending.json'), 'w'))
        self.prev = [self.kings, self.excl, self.closed, self.flagged, self.alive, self.keep]
    def tearDown(self): shutil.rmtree(self.d)

    def _workflow(self, run, carry_log=True):
        """This run's build output: only Keep Hub; Closed Hall closed this run (recently_closed). Then the guard, as in the workflow."""
        new = [dict(self.keep, last_verified=run)]
        closed = [dict(self.closed, closed_on=run)]
        items = new
        if carry_log:
            pend = json.load(open(os.path.join(self.d, 'logs', 'warmspaces_pending.json')))
            items, carried, nc = C.carry_items(self.prev, new, closed, run, excluded=C.excluded_ids(self.d), allowed=set(), pending=pend, valid_until=C.season_end)
            C.write_log(carried, run, root=self.d, not_carried=nc)
        out, rep = G.guard('warmspaces', self.prev, items, run_day=run, closed_ids=[x['id'] for x in closed], root=self.d)
        return {x['id']: x for x in out}, rep

    def _never_back(self, by):
        for i in ('ww-excl', 'ww-closed', 'ww-flagged'): self.assertNotIn(i, by)   # excluded / closed this run / flagged closed
        self.assertIn('ww-keep', by)

    def test_run_2027_05_01_build_then_guard(self):
        by, rep = self._workflow('2027-05-01')
        self._never_back(by)
        self.assertNotIn(KINGS['id'], by)         # season ended (verified 20 Oct 2026, valid to 30 Apr 2027)
        self.assertNotIn('ww-alive', by)          # every 2026-27 verification has expired on 1 May
        self.assertEqual(rep['places'], [])
        lg = json.load(open(os.path.join(self.d, 'logs', 'warmspaces_carry_forward.json')))
        self.assertEqual({r['id']: r['why'] for r in lg['not_carried']}[KINGS['id']], 'season_ended')

    def test_run_2027_05_01_guard_alone(self):  # no carry-forward log this run: the guard applies the same rules itself
        by, rep = self._workflow('2027-05-01', carry_log=False)
        self._never_back(by); self.assertNotIn(KINGS['id'], by); self.assertNotIn('ww-alive', by)
        why = {r['id']: r['why'] for r in rep['not_restored']}
        self.assertEqual(why, {KINGS['id']: 'season_ended', 'ww-excl': 'excluded', 'ww-closed': 'closed', 'ww-flagged': 'closed', 'ww-alive': 'season_ended'})

    def _labelled(self, a):
        self.assertTrue(a['call_check']); self.assertEqual(a['carried_note'], 'Not re-confirmed since 2027-02-20 – call before you go')
        self.assertNotIn('website', a); self.assertEqual(a['website_redirects_to'], 'elsewhere.example'); self.assertTrue(a['review'])

    def test_in_season_build_then_guard(self):
        by, rep = self._workflow('2027-03-01')
        self._never_back(by); self._labelled(by['ww-alive'])
        self.assertEqual(by[KINGS['id']]['carried_note'], 'Not re-confirmed since 2026-10-26 – call before you go')  # in season until 30 Apr: carried, labelled
        self.assertEqual(rep['places'], [])      # build carried them; guard restores nothing

    def test_in_season_guard_alone_restores_labelled(self):
        by, rep = self._workflow('2027-03-01', carry_log=False)
        self._never_back(by); self._labelled(by['ww-alive']); self.assertEqual(by['ww-alive']['guard_kept'], '2027-03-01')
        k = by[KINGS['id']]; self.assertTrue(k['call_check']); self.assertEqual(k['carried_note'], 'Not re-confirmed since 2026-10-26 – call before you go')

    def test_guard_honours_build_not_carried_list(self):
        run = '2027-03-01'
        log = {'run': run, 'carried': [], 'not_carried': [{'id': 'ww-keep2', 'why': 'moved_to:ww-x'}]}
        json.dump(log, open(os.path.join(self.d, 'logs', 'warmspaces_carry_forward.json'), 'w'))
        k2 = dict(self.keep, id='ww-keep2', name='Other Name', postcode='E9 9AA', lat=51.0, lng=0.5)
        out, rep = G.guard('warmspaces', [k2], [], run_day=run, root=self.d)
        self.assertEqual(out, []); self.assertEqual(rep['not_restored'], [{'id': 'ww-keep2', 'why': 'moved_to:ww-x'}])
        log['run'] = '2027-02-28'  # a stale log from another run is not trusted
        json.dump(log, open(os.path.join(self.d, 'logs', 'warmspaces_carry_forward.json'), 'w'))
        out, _ = G.guard('warmspaces', [k2], [], run_day=run, root=self.d)
        self.assertEqual([x['id'] for x in out], ['ww-keep2']); self.assertEqual(out[0]['carried_note'], 'Not re-confirmed since 2027-02-20 – call before you go')

    def test_guard_reads_same_run_log_across_midnight_utc(self):
        """Build writes the log at 23:59 UTC on 28 Feb; the guard runs at 00:01 on 1 Mar in the SAME workflow run."""
        from unittest import mock
        k2 = dict(self.keep, id='ww-keep3', name='Other Name', postcode='E9 9AB', lat=51.0, lng=0.5)
        with mock.patch.dict(os.environ, {'GITHUB_RUN_ID': '777', 'GITHUB_RUN_ATTEMPT': '1'}):
            C.write_log([], '2027-02-28', root=self.d, not_carried=[{'id': 'ww-keep3', 'name': 'Other Name', 'why': 'season_ended'}])
            out, rep = G.guard('warmspaces', [k2], [], run_day='2027-03-01', root=self.d)
        self.assertEqual(out, []); self.assertEqual(rep['not_restored'], [{'id': 'ww-keep3', 'why': 'season_ended'}])
        with mock.patch.dict(os.environ, {'GITHUB_RUN_ID': '778', 'GITHUB_RUN_ATTEMPT': '1'}):  # a different run's log is still not trusted
            out, _ = G.guard('warmspaces', [k2], [], run_day='2027-03-01', root=self.d)
        self.assertEqual([x['id'] for x in out], ['ww-keep3'])

    def test_real_kings_church_entry_stays_out_on_2027_05_01(self):
        ws = open(os.path.join(ROOT, 'warmspaces.js'), encoding='utf-8').read()
        items = json.loads(ws[ws.index('{'):ws.rindex('}') + 1])['items']
        k = next((x for x in items if 'king' in x['name'].lower() and 'halifax' in x['name'].lower()), None)
        if k is None: self.skipTest("King's Church Halifax not in the committed file")
        self.assertEqual(C.why_not(k, '2027-05-01', valid_until=C.season_end), 'season_ended')
        out, rep = G.guard('warmspaces', [k], [], run_day='2027-05-01', root=self.d)
        self.assertEqual(out, [])

if __name__ == '__main__': unittest.main()
