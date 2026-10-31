import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import rest_centre_scan as R


class RestCentreScan(unittest.TestCase):
    def test_on_phrases(self):
        on = [
            "The rest centre has been opened at Riverside Hall for residents.",
            "A rest centre is open at the leisure centre.",
            "The rest centre remains open overnight.",
            "Our reception centre is now available at the civic hall.",
            "An emergency assistance centre opened at 18:00.",
            "The survivor reception centre opened this afternoon.",
        ]
        for t in on:
            self.assertTrue(R.rest_centre_on(t), t)

    def test_off_phrases(self):
        for t in (
            "The rest centre has closed.",
            "The rest centre is now closed.",
            "The rest centre has stood down.",
            "Residents can return to their homes.",
            "The flood warning is no longer in force.",
        ):
            self.assertTrue(R.rest_centre_off(t), t)
            self.assertFalse(R.rest_centre_on(t), t)

    def test_major_or_evac_alone_not_on(self):
        self.assertFalse(R.rest_centre_on("A major incident declared in the borough."))
        self.assertFalse(R.rest_centre_on("Residents are asked to evacuate immediately."))

    def test_humanitarian_alone_ignored(self):
        self.assertFalse(R.rest_centre_on("A humanitarian assistance centre is listed in our plan."))

    def test_swep_ignored_without_rest_centre(self):
        self.assertFalse(R.rest_centre_on("SWEP is active tonight for rough sleepers."))

    def test_planning_page_false_positive(self):
        url = "https://council.example/emergency-plan.pdf"
        text = "Rest centre plan and guidance: what to do if we open a rest centre."
        self.assertTrue(R.is_planning_page(text, url))
        self.assertFalse(R.rest_centre_on(text))


if __name__ == "__main__":
    unittest.main()
