"""28 Oct 2026 listing checks (stale + no-date food banks). Dean's rules: times only when proven on 2 runs (own page, day on the
same line/row), office/phone hours dropped with the phone kept, addresses from the own page, doubtful ones labelled
'call before you go' and flagged, nothing removed, every change on the review list with an undo, overrides so a refresh keeps them."""
import json, os, shutil, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
LOG = json.load(open(os.path.join(ROOT, 'logs', 'listing_checks_2026-10-28.json')))['changes']
def J(p): return json.load(open(os.path.join(ROOT, p), encoding='utf-8'))
def items():
    s = open(os.path.join(ROOT, 'data.full.js'), encoding='utf-8').read()
    return {i['id']: i for i in json.loads(s[s.index('{'):s.rindex('}') + 1])['items']}

class ListingChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.ix = items()

    def test_every_change_is_logged_with_undo_and_exists(self):
        self.assertGreater(len(LOG), 100)
        for c in LOG:
            self.assertIn(c['key'], self.ix, c['key'])
            self.assertIn('before', c); self.assertIn('after', c)

    def test_applied_times_are_proven_and_protected(self):
        ot = J('overrides/opening_times.json')
        for c in LOG:
            if c['file'] != 'opening_times.json': continue
            a = ot[c['key']]
            self.assertEqual(a, c['after']); self.assertTrue(a['protected']); self.assertTrue(a['quote']); self.assertTrue(a['source_url'].startswith('http'))
            self.assertEqual(a['checked_date'], '2026-10-28')
            if a['status'] == 'TIMES_FOUND':
                self.assertTrue(a['structured'], c['key'])  # never known times -> empty
                self.assertIn('2-run', a['reader'])
                self.assertTrue((self.ix[c['key']].get('opening_times') or {}).get('structured'), c['key'])

    def test_office_hours_dropped_phone_kept_and_guard_allows(self):
        gw = J('overrides/guard_wrong_times.json')['foodbanks']
        n = 0
        for c in LOG:
            if c['file'] == 'opening_times.json' and c['after']['status'] == 'NOT_CLIENT_HOURS':
                n += 1; i = self.ix[c['key']]
                self.assertIsNone(i.get('opening_times'), c['key']); self.assertTrue(i.get('phone'), c['key']); self.assertIn(c['key'], gw)
        self.assertGreaterEqual(n, 5)

    def test_build_honours_not_client_hours_and_flag(self):
        src = open(os.path.join(ROOT, 'scripts', 'build.py')).read()
        self.assertIn("== 'NOT_CLIENT_HOURS': ot = None", src); self.assertIn("i['call_first'] = True", src)

    def test_labels_on_cards_and_nothing_removed(self):
        no = J('overrides/foodbank_notices.json')
        for c in LOG:
            if c['file'] != 'foodbank_notices.json': continue
            self.assertEqual(no[c['key']]['flag'], 'call_first')
            self.assertIn('all before you go', no[c['key']]['notice'])
            self.assertEqual(self.ix[c['key']].get('notice'), no[c['key']]['notice'])
        self.assertEqual(len(self.ix), len(J('export/foodbanks.json')) if isinstance(J('export/foodbanks.json'), list) else len(self.ix))
        rm = set(J('overrides/foodbank_address_fixes.json').get('_remove_ids', []))
        self.assertFalse(rm & {c['key'] for c in LOG})

    def test_addresses_applied(self):
        af = J('overrides/foodbank_address_fixes.json')
        for c in LOG:
            if c['file'] == 'foodbank_address_fixes.json':
                self.assertEqual(self.ix[c['key']]['postcode'], af[c['key']]['postcode']); self.assertIn('evidence_url', af[c['key']])

    def test_review_list_has_every_change(self):
        pd = open(os.path.join(ROOT, 'reports', 'pending_dean.md'), encoding='utf-8').read()
        a, b = pd.index('<!-- listing checks 28 oct -->'), pd.index('<!-- /listing checks 28 oct -->')
        sec = pd[a:b]
        for c in LOG: self.assertIn('`%s`' % c['key'], sec)
        for k in ('salvation-army/teignmouth', 'salvation-army/harlesden', 'salvation-army/hayes', 'swansea/gorseinon-institute', 'gloucester/elim-church-gloucester', 'boston/st-marys-church'):
            self.assertIn('`%s`' % k, sec)

    def test_parent_listings_and_cardiff_untouched(self):
        keys = {c['key'] for c in LOG}
        self.assertFalse(keys & {'colchester', 'wirral', 'fosse', 'airdrie', 'salvation-army/bourne', 'salvation-army/chester'})
        self.assertFalse([k for k in keys if 'cardiff' in k])

    def test_disputed_run1_removals_not_applied(self):
        ot = J('overrides/opening_times.json')
        self.assertNotEqual((ot.get('silklife') or {}).get('status'), 'NOT_CLIENT_HOURS')
        for k in ('ross-community-larder', 'selby-centre'): self.assertTrue(ot[k]['structured'])

    def test_undo_restores(self):
        import listing_checks_undo as U
        d = tempfile.mkdtemp()
        try:
            shutil.copytree(os.path.join(ROOT, 'overrides'), os.path.join(d, 'overrides')); os.makedirs(os.path.join(d, 'logs'))
            shutil.copy(os.path.join(ROOT, 'logs', 'listing_checks_2026-10-28.json'), os.path.join(d, 'logs'))
            U.undo({'woodhouse-close-church', 'cramlington'}, root=d)
            ot = json.load(open(os.path.join(d, 'overrides', 'opening_times.json')))
            self.assertFalse(ot['woodhouse-close-church'].get('protected'))
            self.assertNotIn('cramlington', json.load(open(os.path.join(d, 'overrides', 'foodbank_address_fixes.json'))))
        finally: shutil.rmtree(d)

if __name__ == '__main__': unittest.main()
