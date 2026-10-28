"""Offline Playwright checks for Show more.

The page contract is window.SHOW_LIMITS = {first: 5, more: 10} and
window.showMoreResults(), with the results in #list as .card elements.
scripts/showmore_journey.py drives a local server; tiles come from main's
scripts/offline_tiles.py (PR 157), so no tile host is ever contacted.
The plain pytest job has no browser, so the journey is skipped there; the
host list and the reveal rules still run.
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import showmore_journey as J


class Rules(unittest.TestCase):
    def test_tile_hosts(self):
        for url in (
            'https://tile.openstreetmap.org/6/31/20.png',
            'https://a.tile.openstreetmap.org/1/0/0.png',
            'https://tiles.openfreemap.org/planet/1/2/3.png',
            'https://api.maptiler.com/maps/streets-v2/256/1/2/3.png?key=abc',
            'https://tiles.stadiamaps.com/tiles/osm_bright/1/2/3.png?api_key=x',
        ):
            self.assertTrue(J.is_tile_url(url), url)
        for url in (
            'http://127.0.0.1/tiles.js',
            'https://helpmap.uk/',
            'https://www.openstreetmap.org/copyright',
            'https://api.postcodes.io/places?q=York',
        ):
            self.assertFalse(J.is_tile_url(url), url)

    def test_first_reveal_is_ten_more(self):
        self.assertIsNone(J.reveal_ok(5, 15, 2812, 10, 0))
        self.assertIsNotNone(J.reveal_ok(5, 6, 2812, 10, 0))
        self.assertIsNotNone(J.reveal_ok(5, 2812, 2812, 10, 0))  # the first press is 10, not the rest

    def test_later_press_may_show_the_rest(self):
        self.assertIsNone(J.reveal_ok(15, 25, 2812, 10, 1))
        self.assertIsNone(J.reveal_ok(15, 2812, 2812, 10, 1))  # "then the rest"
        self.assertIsNone(J.reveal_ok(25, 30, 30, 10, 2))  # a short last page
        self.assertIsNotNone(J.reveal_ok(25, 30, 100, 10, 2))
        self.assertIsNotNone(J.reveal_ok(15, 14, 2812, 10, 1))

    def test_button_hides_only_at_the_end(self):
        self.assertIsNone(J.button_ok(5, 2812, True))
        self.assertIsNone(J.button_ok(2812, 2812, False))
        self.assertIsNotNone(J.button_ok(15, 2812, False))
        self.assertIsNotNone(J.button_ok(2812, 2812, True))

    def test_blank_png_is_a_png(self):
        self.assertTrue(J.PNG.startswith(b'\x89PNG\r\n\x1a\n'))


@unittest.skipUnless(J.available(), 'needs chrome + playwright')
class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = J.run()

    def _ok(self, name):
        for row in self.out.rows:
            if row['name'] == name:
                self.assertTrue(row['ok'], '%s: %s' % (name, row['why']))
                return
        failed = ['%s: %s' % (r['name'], r['why']) for r in self.out.rows if not r['ok'] and r['name'] != '_net']
        self.fail('no result for %s\n%s' % (name, '\n'.join(failed)))

    def test_contract(self):
        self._ok('contract')

    def test_exactly_five_cards(self):
        self._ok('exactly 5 cards')

    def test_button_reveals_ten_more(self):
        self._ok('button reveals 10 more')

    def test_then_the_rest(self):
        self._ok('then the rest')

    def test_button_hides_at_the_end(self):
        self._ok('button hides at the end')

    def test_new_search_resets_to_five(self):
        self._ok('new search resets to 5')

    def test_near_me_littlehampton(self):
        self._ok('near me Littlehampton')
        self._ok('near me show more')

    def test_phone_width(self):
        self._ok('phone 360')
        self._ok('phone 360 show more')
        self._ok('phone button readable')

    def test_dark_mode(self):
        self._ok('dark mode')

    def test_welsh(self):
        self._ok('welsh')
        self._ok('welsh show more')
        self._ok('welsh button readable')

    def test_no_real_tile_request(self):
        self._ok('no real tile request')
        self._ok('stayed off the live site')


if __name__ == '__main__':
    unittest.main()
