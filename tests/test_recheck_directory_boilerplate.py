import json, os, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import recheck

FILLER = "Project 394 is for women who are new to rough sleeping with medium to high support needs. " * 5
BOILER = "If you have noticed outdated information, or a service is no longer running, please let us know using the button."
URL = "https://www.manchesterservicedirectory.co.uk/kb5/manchester/directory/service.page?id=TtFEY2JXDos"


def page(text):
    return {"http": 200, "text": text, "final_url": URL, "sha256": "x"}


class Project394DirectoryBoilerplate(unittest.TestCase):
    """The directory's feedback line is not a closure; a real closure notice on the same page still is."""
    entry = {"id": "man-ss-riverside-project-394", "name": "Project 394 (Riverside, women)", "postcode": "M20 4BH"}

    def setUp(self):
        self.ov = json.load(open(os.path.join(ROOT, "overrides", "shelters_verified.json"), encoding="utf-8"))[self.entry["id"]]

    def test_feedback_boilerplate_is_not_a_closure(self):
        r = recheck.check(self.entry, self.ov, page(FILLER + BOILER), url=URL)
        self.assertFalse(r["closed_words"])

    def test_without_the_exception_it_would_trip(self):
        self.assertTrue(recheck.check(self.entry, {}, page(FILLER + BOILER), url=URL)["closed_words"])

    def test_real_closure_still_detected(self):
        for notice in ("Project 394 is no longer running.", "This service has permanently closed.", "The service has ended."):
            r = recheck.check(self.entry, self.ov, page(FILLER + notice + " " + BOILER), url=URL)
            self.assertTrue(r["closed_words"], notice)
            self.assertEqual(r["reason"], "source now says closed/ended")


if __name__ == "__main__":
    unittest.main()
