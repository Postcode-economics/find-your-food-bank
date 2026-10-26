"""Rule 7. A closed shelter and a food bank that leaves the feed wait for Dean. Nothing is deleted here."""
import os, tempfile, unittest
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import pending_hold

ROOT = os.path.join(os.path.dirname(__file__), '..')


class Hold(unittest.TestCase):
    def test_closed_shelter_stays_in_the_list(self):
        fresh = [
            {'id': 's1', 'name': 'Night', 'website': 'https://example.test/s', '_own_site_closed': 'permanently closed'},
            {'id': 's2', 'name': 'Open'},
        ]
        held = pending_hold.hold_closed_shelters(fresh)
        self.assertEqual([x['id'] for x in fresh], ['s1', 's2'])
        self.assertNotIn('_own_site_closed', fresh[0])
        self.assertEqual(held[0]['id'], 's1')
        self.assertEqual(held[0]['evidence'], 'permanently closed')
        body = pending_hold.shelter_closure_body(held)
        self.assertIn('still on the map', body)
        self.assertIn('s1', body)

    def test_feed_drop_is_listed_and_not_a_removal(self):
        self.assertEqual(pending_hold.feed_drop_ids(['a', 'gone'], ['a', 'b']), ['gone'])
        self.assertEqual(pending_hold.feed_drop_ids([], ['a']), [])
        body = pending_hold.feed_drop_body(['gone'])
        self.assertIn('dropped out of the feed', body)
        self.assertIn('not recorded as removed', body)

    def test_marked_section_is_replaced_and_a_phone_hold_omits_the_number(self):
        path = os.path.join(tempfile.mkdtemp(), 'pending_dean.md')
        pending_hold.write_marked(path, 'shelter closures', pending_hold.shelter_closure_body(
            [{'id': 's1', 'name': 'Night', 'evidence': 'closed', 'website': 'https://example.test/s'}]))
        pending_hold.write_marked(path, 'feed drops', pending_hold.feed_drop_body(['gone']))
        pending_hold.write_marked(path, 'shelter closures', pending_hold.shelter_closure_body([]))
        pending_hold.write_marked(path, 'phone holds', pending_hold.phone_hold_body(
            [{'id': 'x', 'name': 'X', 'website': 'https://example.test/x', 'why': 'page says no phone calls'}]))
        text = open(path, encoding='utf-8').read()
        self.assertEqual(text.count('<!-- shelter closures -->'), 1)
        self.assertIn('- none', text)
        self.assertIn('gone', text)
        self.assertIn('page says no phone calls', text)
        self.assertNotIn('01234', text)

    def test_builders_send_closures_and_feed_drops_to_the_pending_list(self):
        shelters = open(os.path.join(ROOT, 'scripts', 'build_shelters.py'), encoding='utf-8').read()
        self.assertIn('hold_closed_shelters(fresh)', shelters)
        self.assertIn('"removed_closed": []', shelters)
        self.assertIn('pending_closed', shelters)
        self.assertNotIn('if not x.pop("_own_site_closed"', shelters)
        check = open(os.path.join(ROOT, 'scripts', 'full_check.py'), encoding='utf-8').read()
        self.assertIn("kind='feed drop'", check)
        self.assertNotIn("kind='removed'", check)
        self.assertIn("pending_hold.feed_drop_body(feed_drops)", check)


if __name__ == '__main__':
    unittest.main()
