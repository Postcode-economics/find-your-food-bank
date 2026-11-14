"""A carried card without a readable last_verified date is counted as stale; it never crashes the rebuild (14 Nov 2026, rule 82)."""
import os, sys, unittest
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from common import merge_lifecycle


def card(i, **kw):
    x = {"id": i, "name": i}
    x.update(kw)
    return x


class MissingDate(unittest.TestCase):
    def test_missing_or_bad_date_is_stale_not_a_crash(self):
        prev = {"items": [card("a"), card("b", last_verified=""), card("c", last_verified="not a date"),
                          card("d", last_verified="2026-11-13")], "recently_closed": []}
        items, closed = merge_lifecycle(prev, [card("e", last_verified="2026-11-14")], "2026-11-14")
        stale = {x["id"]: x["stale"] for x in items}
        self.assertEqual(stale, {"a": True, "b": True, "c": True, "d": False, "e": False})
        self.assertEqual(closed, [])

    def test_carried_cards_are_kept(self):
        prev = {"items": [card("a")], "recently_closed": []}
        items, _ = merge_lifecycle(prev, [], "2026-11-14")
        self.assertEqual([x["id"] for x in items], ["a"])


if __name__ == "__main__":
    unittest.main()
