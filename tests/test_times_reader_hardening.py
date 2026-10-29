"""What the times reader accepts as opening hours, from the check-only intelligent sweep of 29 Oct 2026.

Each case is a real reading from that run. Haverhill, Silklife and Exeter are the live page text saved that day
(tests/fixtures/sweep_check_2026-10-29). Eyres Monsell and Purley answered HTTP 202 to a re-fetch, so their text is
rebuilt from the readings logged in logs/times_finder.json on that run. Every rejected span is logged with its reason."""
import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import discover as D, times_finder as F, trussell_times as TT

FX = os.path.join(os.path.dirname(__file__), "fixtures", "sweep_check_2026-10-29")
def fx(name): return open(os.path.join(FX, name + ".txt"), encoding="utf-8").read()

TRINITY = ("Follow Us Open Times We accept phone calls Mon-Thurs 10am - 2pm only from Statuatory agencies We are open for "
           "collection of food parcels, advice, signposting Friday 9 - 12 Facebook Trinity Food Bank")
TRINITY_OT = {"status": "TIMES_FOUND", "structured": {"mon": [["10:00", "14:00"]], "tue": [["10:00", "14:00"]], "wed": [["10:00", "14:00"]],
              "thu": [["10:00", "14:00"]], "fri": [["09:00", "12:00"]]}, "raw": "Mon-Thurs 10am - 2pm | Friday 9 - 12"}
EYRES = ("Contact Us Eyres Monsell Club for Young People, Leicester LE2 9AQ. Gym opening times Monday 6:30am – 9:00pm "
         "Tuesday 6:30am – 9:00pm Wednesday 6:30am – 9:00pm Thursday 8:00am – 9:00pm Friday 8:00am – 8:00pm Saturday 8:00am – 4:00pm "
         "Sunday 8:00am – 2:00pm. Centre opening hours Monday 9:00am – 2:00pm Tuesday 9:00am – 2:00pm Wednesday 9:00am – 2:00pm "
         "Thursday 9:00am – 2:00pm Friday 9:00am – 2:00pm Saturday 9:00am – 1:00pm.")
PURLEY_RAW = ("Tuesdays 10am-4pm | Wednesdays 12pm-4pm | Monday-Friday 9am-5pm | Fridays 9am-12pm | Thursdays 9.15am-12.45pm | "
              "Wednesdays 10-11.30am | Wednesdays and Saturdays 10am-12pm")


def week(**days): return {"status": "TIMES_FOUND", "structured": {d: [list(s) for s in v] for d, v in days.items()}}


class NonClientHours(unittest.TestCase):
    def test_trinity_agency_phone_line_is_not_opening_hours(self):
        rej = []
        got = D.extract_times(TRINITY, None, rejected=rej)
        self.assertEqual(got["structured"], {"fri": [["09:00", "12:00"]]})
        self.assertEqual([r["text"] for r in rej], ["Mon-Thurs 10am - 2pm"])
        self.assertIn("phone calls", rej[0]["reason"])

    def test_trinity_stored_mon_thu_is_no_longer_confirmed(self):
        st, _, why = D.confirm_times(TRINITY_OT, [TRINITY], None, pages=[("https://trinityfoodbank.co.uk/", TRINITY)],
                                     source_url="https://trinityfoodbank.co.uk/")
        self.assertNotEqual(st, "confirmed", why)

    def test_agency_only_line_after_the_times_is_rejected(self):
        rej = []
        got = D.extract_times("Referral line Tuesday 9am - 11am for agencies only. Collection Thursday 1pm - 3pm.", None, rejected=rej)
        self.assertEqual(got["structured"], {"thu": [["13:00", "15:00"]]})
        self.assertEqual(rej[0]["reason"], "agency/professional-only line")

    def test_clients_referred_by_agencies_are_still_client_times(self):
        got = D.extract_times("Open Tuesday 10am - 12pm for clients referred by support agencies. Thursday 1pm - 3pm.", None)
        self.assertEqual(got["structured"], {"tue": [["10:00", "12:00"]], "thu": [["13:00", "15:00"]]})

    def test_haverhill_contact_and_adviser_hours_are_rejected(self):
        rej = []
        self.assertIsNone(D.extract_times(fx("haverhill"), "CB9 8SA", rejected=rej))
        self.assertEqual({r["reason"] for r in rej}, {"non-client hours (contact hours)", "non-client hours (adviser)"})

    def test_eyres_monsell_gym_and_centre_hours_are_rejected(self):
        rej = []
        self.assertIsNone(D.extract_times(EYRES, "LE2 9AQ", rejected=rej))
        self.assertEqual(len(rej), 13)
        self.assertTrue(rej[0]["reason"].startswith("non-client hours (gym"), rej[0])
        self.assertTrue(rej[7]["reason"].startswith("non-client hours (centre opening hours"), rej[7])

    def test_other_non_client_hours(self):
        for text in ("Our preschool sessions run Monday 9am - 12pm.", "Café open Tuesday 10am - 2pm.",
                     "Helpline Monday 9am - 5pm.", "Donation drop-off Wednesday 10am - 12pm.",
                     "Church services: Sunday 10:30am - 12:30pm.", "Coffee morning Friday 10am - 12pm."):
            rej = []
            self.assertIsNone(D.extract_times(text, None, rejected=rej), text)
            self.assertTrue(rej and rej[0]["reason"].startswith("non-client hours"), (text, rej))


class Jumble(unittest.TestCase):
    def test_purley_many_blocks_is_review_only(self):
        self.assertIn("7 separate time blocks", D.jumble_reason({"raw": PURLEY_RAW}))
        ot = {"status": "TIMES_FOUND", "structured": {"tue": [["10:00", "16:00"]]}, "raw": PURLEY_RAW, "source_url": "https://www.purleyfoodhub.net/get-help/",
              "pc_seen": ["CR84BQ"], "reader": "times_finder", "fb_mention": True}
        item = {"id": "purley/cr8", "name": "CR8", "postcode": "CR8 4BQ", "website": "https://www.purleyfoodhub.net/"}
        why = F.strict_checks("purley/cr8", ot, item, {}, {}, 1, {"pages": {}, "skip": {}}, {}, {})
        self.assertTrue(any(w.startswith("jumble") for w in why), why)

    def test_same_day_with_different_times_is_a_jumble(self):
        self.assertIn("Wed", D.jumble_reason({"raw": "Wednesday 10am - 12pm | Wednesday 2pm - 4pm"}))

    def test_one_clear_table_is_not_a_jumble(self):
        self.assertEqual(D.jumble_reason({"raw": "Tuesdays 13:30 - 15:00 | Fridays 13:30 - 15:00"}), "")
        self.assertEqual(D.jumble_reason({"raw": "Wednesday 10am - 12pm | Wednesdays 10am - 12pm"}), "")   # Lyme Regis: same block twice

    def test_jumble_is_held_on_the_refresh_gate(self):
        i = {"id": "x", "name": "X Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/", "opening_times": week(tue=[("10:00", "12:00")])}
        new = dict(week(tue=[("10:00", "16:00")]), raw=PURLEY_RAW)
        why = D.times_gate_reasons(i, "fb", "opening_times", new, ["X Food Bank AB1 2CD " + PURLEY_RAW], {"final_url": "https://x.org/"},
                                   {}, {}, True, "2026-10-29T11:00:00+00:00", own_sites={})
        self.assertTrue(any(w.startswith("jumble") for w in why), why)


class PerCentre(unittest.TestCase):
    def test_exeter_locations_page_binds_each_centre_to_its_own_times(self):
        t = fx("exeter")
        self.assertEqual(D.extract_times(t, "EX5 7EE")["structured"], {"thu": [["17:00", "19:00"]]})
        self.assertEqual(D.extract_times(t, "EX4 8LZ")["structured"], {"wed": [["10:00", "12:00"]], "fri": [["10:00", "12:00"]]})
        rej = []
        self.assertIsNone(D.extract_times(t, "EX1 1AA", rejected=rej))   # a centre that is not on the page gets nothing
        self.assertIn("postcode", rej[0]["reason"])

    def test_single_centre_fallback_never_reads_a_multi_centre_page(self):
        pages = [("https://exeterfoodbank.co.uk/", "Exeter Foodbank home"), ("https://exeterfoodbank.co.uk/opening-times/", fx("exeter"))]
        old = F.site_texts
        F.site_texts = lambda base, maxpages=10: (200, base, pages)
        try:
            out = F.generic([{"id": "e", "name": "Exeter Foodbank", "postcode": "EX2 9ZZ", "website": "https://exeterfoodbank.co.uk/"}], "https://exeterfoodbank.co.uk/")
        finally:
            F.site_texts = old
        ot, why = out["e"]
        self.assertIsNone(ot)
        self.assertIn("several centres", why)

    def test_woking_card_is_taken_only_by_postcode(self):
        cards = [{"name": "Woking Foodbank (Town Centre)", "postcode": "GU21 6EL"}, {"name": "Woking Foodbank Byfleet", "postcode": "KT14 7LL"},
                 {"name": "Woking Foodbank Sheerwater", "postcode": "GU21 5NZ"}, {"name": "Woking Foodbank Sythwood", "postcode": "GU21 3BE"}]
        self.assertEqual(TT.match({"name": "Woking Foodbank", "postcode": "GU21 6EL"}, cards), (cards[0], "postcode"))
        self.assertEqual(TT.match({"name": "Woking Foodbank", "postcode": "GU22 7AA"}, cards)[0], None)


class NoDayTable(unittest.TestCase):
    def test_silklife_is_unreadable_and_nothing_is_guessed(self):
        t = fx("silklife")
        rej = []
        self.assertIsNone(D.extract_times(t, "SK11 6HS", rejected=rej))   # the only spans are donation drop-off and the Sunday service
        self.assertTrue(rej and all(r["reason"].startswith("non-client hours") for r in rej), rej)
        stored = week(tue=[("10:30", "12:30")], fri=[("10:30", "12:30")], sat=[("10:30", "12:30")], sun=[("10:30", "12:30")])
        st, new, why = D.confirm_times(stored, [t], "SK11 6HS", pages=[("https://www.silklife.co.uk/foodbank", t)], source_url="https://www.silklife.co.uk/foodbank")
        self.assertEqual((st, new), ("differs_review", None))
        self.assertTrue(why.startswith("unreadable"), why)


class NeverShrink(unittest.TestCase):
    def test_apsley_and_galashiels_fewer_days_are_held(self):
        apsley = D.shrink_reason(week(mon=[("15:30", "17:30")], thu=[("10:00", "12:00")]), week(thu=[("10:00", "12:00")]), ["Thursday 10am - 12pm"])
        self.assertIn("drops Mon", apsley)
        gala = D.shrink_reason(week(wed=[("13:00", "14:45")], thu=[("17:00", "18:00")]), week(wed=[("13:00", "14:45")]), [""])
        self.assertIn("drops Thu", gala)

    def test_two_days_to_one_on_two_identical_runs_is_still_held(self):
        import tempfile
        from test_hours_confirm import fake, page, week_of, WED, R1, R2, ON
        root = tempfile.mkdtemp()
        def item():
            return [{"id": "a", "name": "Riverside Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/",
                     "opening_times": {"status": "TIMES_FOUND", "structured": {"tue": [["10:00", "12:00"]], "fri": [["13:00", "15:00"]]}}}]
        f = fake({"https://x.org/": page(week_of(WED))})
        for run_at in (R1, R2):
            it = item(); log = D.cross_check_times(it, "fb", "opening_times", f, state_root=root, rules=ON, run_at=run_at)
        self.assertEqual(log["a"]["status"], "held_for_dean")
        self.assertTrue(any("fewer days (drops Tue, Fri)" in w for w in log["a"]["held"]))
        self.assertEqual(it[0]["opening_times"]["structured"], {"tue": [["10:00", "12:00"]], "fri": [["13:00", "15:00"]]})

    def test_source_saying_the_session_ended_allows_fewer_days(self):
        self.assertEqual(D.shrink_reason(week(mon=[("15:30", "17:30")], thu=[("10:00", "12:00")]), week(thu=[("10:00", "12:00")]),
                                         ["The Monday session has now ended. Thursday 10am - 12pm."]), "")

    def test_more_or_moved_days_are_not_a_shrink(self):
        self.assertEqual(D.shrink_reason(week(wed=[("11:00", "13:00")]), week(thu=[("11:00", "13:00")])), "")   # Thurrock-style move
        self.assertEqual(D.shrink_reason(week(mon=[("09:30", "12:30")]), week(mon=[("09:30", "12:30")], sat=[("09:30", "12:30")])), "")

    def test_warm_space_hours_dict_counts_days(self):
        self.assertIn("drops Fri", D.shrink_reason({"Wed": "10:00 - 12:00", "Fri": "10:00 - 12:00"}, week(wed=[("10:00", "12:00")])))

    def test_shrink_is_held_on_both_gates(self):
        i = {"id": "x", "name": "X Food Bank", "postcode": "AB1 2CD", "website": "https://x.org/",
             "opening_times": week(mon=[("15:30", "17:30")], thu=[("10:00", "12:00")])}
        new = dict(week(thu=[("10:00", "12:00")]), raw="Thursday 10am - 12pm")
        why = D.times_gate_reasons(i, "fb", "opening_times", new, ["X Food Bank AB1 2CD Thursday 10am - 12pm"], {"final_url": "https://x.org/"},
                                   {}, {}, True, "2026-10-29T11:00:00+00:00", own_sites={})
        self.assertTrue(any("fewer days" in w for w in why), why)
        ot = dict(new, source_url="https://x.org/", pc_seen=["AB12CD"], reader="times_finder", fb_mention=True)
        why = F.strict_checks("x", ot, i, {}, {}, 1, {"pages": {}, "skip": {}}, {}, {})
        self.assertTrue(any("fewer days" in w for w in why), why)


class RejectionsAreLogged(unittest.TestCase):
    def test_cross_check_log_keeps_each_rejected_span_and_reason(self):
        import tempfile
        h = "<html><body><h1>Trinity Food Bank</h1><p>M26 3WD. %s</p></body></html>" % TRINITY
        page = {"http": 200, "final_url": "https://trinityfoodbank.co.uk/", "html": h, "etag": "", "last_modified": "", "sha256": "x"}
        it = [{"id": "trinity", "name": "Trinity Foodbank", "postcode": "M26 3WD", "website": "https://trinityfoodbank.co.uk/", "opening_times": dict(TRINITY_OT)}]
        log = D.cross_check_times(it, "fb", "opening_times", lambda u: page, state_root=tempfile.mkdtemp(), rules={"times_auto_apply": False},
                                  run_at="2026-10-29T11:00:00+00:00")
        self.assertNotEqual(log["trinity"]["status"], "confirmed")
        self.assertIn({"text": "Mon-Thurs 10am - 2pm", "reason": "non-client hours (accept phone calls)"}, log["trinity"]["rejected"])


if __name__ == "__main__":
    unittest.main()
