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
        orig = (F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP)
        F.rj = lambda n, d: store.get(n, d)
        F.wj = lambda n, o: written.__setitem__(n, o)
        F.load_data = lambda: ('x=', {'items': items})
        F.load_access = lambda: {}
        F.write_md = lambda today, log, stats: md.update(log=log, stats=stats)
        F.REP = tempfile.mkdtemp()
        os.environ['DRY_RUN'] = '1'
        try: F.main()
        finally:
            F.rj, F.wj, F.load_data, F.load_access, F.write_md, F.REP = orig; os.environ.pop('DRY_RUN')
        kinds = {(e['id'], e['kind']) for e in md['log']}
        self.assertIn(('b', 'new food bank'), kinds); self.assertIn(('gone', 'removed'), kinds)
        self.assertEqual(written['full_check_state.json']['ids'], ['a', 'b'])
        self.assertTrue(written['daily_review.json'][F.DAY]['runs'])

if __name__ == '__main__': unittest.main()
