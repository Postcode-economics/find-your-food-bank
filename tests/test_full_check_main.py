"""Regression (25 Oct 2026): main() crashed with UnboundLocalError 'log' whenever a food bank was added/removed vs last run."""
import sys, os, unittest, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import full_check as F

class T(unittest.TestCase):
    def test_new_and_removed_path(self):
        items = [dict(id='a', type='foodbank', name='A', foodbank='A', website='', postcode='X1'),
                 dict(id='b', type='foodbank', name='B', foodbank='B', website='', postcode='X2')]
        store = {'full_check_state.json': {'sites': {}, 'ids': ['a', 'gone']}}
        written, md = {}, {}
        rep = tempfile.mkdtemp()
        orig = (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP)
        F.rj = lambda n, d: store.get(n, d)
        F.wj = lambda n, o: written.__setitem__(n, o)
        F.load_data = lambda: ('x=', {'items': items})
        F.load_access = lambda: {}
        F.write_md = lambda today, log, stats: md.update(log=log, stats=stats)
        F.REP = rep
        os.environ['DRY_RUN'] = '1'
        try: F.main()
        finally:
            F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP = orig; os.environ.pop('DRY_RUN')
        kinds = {(e['id'], e['kind']) for e in md['log']}
        self.assertIn(('b', 'new food bank'), kinds)
        self.assertNotIn(('gone', 'removed'), kinds)  # a feed drop is not a removal (rule 7)
        self.assertEqual(written['full_check_state.json']['ids'], ['a', 'b'])
        self.assertTrue(written['daily_review.json'][F.DAY]['runs'])
        pending = open(os.path.join(rep, 'pending_dean.md'), encoding='utf-8').read()
        self.assertIn('gone', pending)
        self.assertIn('dropped out of the feed', pending)
        self.assertNotIn('kind\': \'removed\'', pending)
        cats = {v['category'] for v in written['daily_review.json'][F.DAY]['items'].values()}
        self.assertIn('dropped out of the feed', cats)

    def test_page_that_forbids_calls_holds_the_number(self):
        items = [dict(id='a', type='foodbank', name='A', foodbank='A', website='https://a.example',
                      postcode='X1', phone='01234 567890', tel='01234567890')]
        store = {'full_check_state.json': {'sites': {}, 'ids': ['a']}}
        written = {}; rep = tempfile.mkdtemp()
        orig = (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site)
        F.rj = lambda n, d: store.get(n, d)
        F.wj = lambda n, o: written.__setitem__(n, o)
        F.load_data = lambda: ('x=', {'items': items})
        F.load_access = lambda: {}
        F.write_md = lambda *a: None
        F.REP = rep
        F.check_site = lambda u: dict(url=u, ok=True, final_url=u, access='unclear', hours_hash=None,
                                       hours_sample=None, seasonal=None, closed=None, perm_closed=None,
                                       phones=['01234567890'], tel=None, needs=None, checked_at='y', http=200,
                                       text='Please do not call.')
        os.environ['DRY_RUN'] = '1'
        try: F.main()
        finally:
            F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP, F.check_site = orig
            os.environ.pop('DRY_RUN', None)
        self.assertEqual(items[0]['phone'], '')
        self.assertEqual(items[0]['tel'], '')
        self.assertNotIn('phone_label', items[0])
        pending = open(os.path.join(rep, 'pending_dean.md'), encoding='utf-8').read()
        self.assertIn('page says no phone calls', pending)
        self.assertNotIn('01234', pending)
        self.assertNotIn('567890', pending)

if __name__ == '__main__': unittest.main()
