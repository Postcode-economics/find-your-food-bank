import os, sys, json, tempfile, unittest, datetime
from unittest import mock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import common


class KeptCopyGetsManualFields(unittest.TestCase):
    """A published manual entry whose own site is blocked keeps its listing, with this run's hand fields applied."""

    def test_blocked_site_still_gets_manual_fields(self):
        old = {"id": "man-ss-x", "name": "Old", "phone": "0161 000 0000", "referral": "old", "facilities": "Not stated",
               "groups": [], "fetched_at": "2026-11-01T00:00:00+00:00"}
        new = {"id": "man-ss-x", "name": "New", "phone": "0345 111 0000", "phone_label": "24/7 line", "referral": "new route",
               "facilities": ["Laundry"], "groups": ["Men aged 18 and over"], "beds": "38", "hours": "24/7",
               "discovery_label": "Street Support", "source_url": "https://own.example/"}
        ver = {"man-ss-x": {"evidence_url": "https://own.example/", "quote": "q", "verified_on": "2026-11-03", "access": "new route"}}
        with tempfile.TemporaryDirectory() as d, mock.patch("recheck.recheck_all", return_value={"man-ss-x": {"ok": False, "http": 403, "reason": "HTTP 403"}}), \
                mock.patch.object(common, "record_layer_holds", lambda *a, **k: None):
            res = common.verification_gate([new], {"items": [old]}, ver, "2026-11-04", os.path.join(d, "shelters_pending.json"),
                                              now=datetime.datetime(2026, 11, 4, tzinfo=datetime.timezone.utc))
        x = res[0][0]
        self.assertTrue(x.get("kept_fetch_blocked"))
        for k in ("name", "phone", "phone_label", "facilities", "groups", "beds", "hours", "discovery_label", "source_url"):
            self.assertEqual(x.get(k), new[k], k)
        self.assertEqual(x["referral"], "New route")


if __name__ == "__main__":
    unittest.main()
