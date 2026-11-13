"""erc-live alert: one GitHub issue when a REAL rest centre goes live, never for tests, never on every refresh (12 Nov 2026).
Also: a refresh that starts without live state keeps the public file's rest centres (no wipe, no resurrection)."""
import datetime, json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import erc_live_alert as ea  # noqa: E402

NOW = datetime.datetime(2026, 11, 12, 22, 0, tzinfo=datetime.timezone.utc)


def card(name="Civic Hall", council="Exeter City Council", **kw):
    c = {"name": name, "council": council, "live": True, "category": "incident_rest_centre", "lad": "E07000041",
         "source_url": "https://example.invalid/rest-centre", "address": "EX1 1HS", "open_until": "2099-01-01T00:00:00+00:00"}
    c.update(kw)
    return c


def payload(*cards, public=True):
    return {"public": public, "cards": list(cards)}


class FakeGh:
    def __init__(self, issues=None):
        self.calls, self.issues = [], issues or []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "list"):
            return json.dumps(self.issues)
        return ""

    def created(self):
        return [a for a in self.calls if a[:2] == ("issue", "create")]


class WhatCounts(unittest.TestCase):
    def test_test_cards_never_alert(self):
        for c in (card(name="TEST Village Hall - do not travel"), card(opened_for="a TEST only"),
                  card(test=True), card(example=True), card(quote="helpmap.uk system test, not real"),
                  card(name="Village Hall", opened_for="system test")):
            self.assertEqual(ea.newly_live(payload(), payload(c)), [], c)

    def test_real_card_off_to_on_is_new(self):
        self.assertEqual(len(ea.newly_live(payload(), payload(card()))), 1)

    def test_already_live_is_not_new(self):
        self.assertEqual(ea.newly_live(payload(card()), payload(card())), [])

    def test_not_public_is_never_new(self):
        self.assertEqual(ea.newly_live(payload(), payload(card(), public=False)), [])

    def test_ordinary_word_test_in_lower_case_is_real(self):
        self.assertEqual(len(ea.newly_live(payload(), payload(card(name="Testwood Community Centre")))), 1)


class Issue(unittest.TestCase):
    def test_title_and_label(self):
        gh = FakeGh()
        r = ea.notify(payload(), payload(card()), gh=gh, now=NOW)
        self.assertEqual(r["opened"], 1)
        (args,) = gh.created()
        t = args[args.index("--title") + 1]
        self.assertRegex(t, r"^Rest centre live on helpmap\.uk: Exeter City Council - Civic Hall \[erc:[0-9a-f]{10}\]$")
        self.assertEqual(args[args.index("--label") + 1], "erc-live")
        b = args[args.index("--body") + 1]
        self.assertIn("@Postcode-economics", b)
        self.assertIn("E07000041", b)

    def test_once_per_incident_while_open(self):
        k = ea.card_key(card())
        gh = FakeGh([{"number": 1, "title": "x [erc:%s]" % k, "state": "OPEN", "createdAt": "2026-11-01T00:00:00Z"}])
        self.assertEqual(ea.notify(payload(), payload(card()), gh=gh, now=NOW)["opened"], 0)
        self.assertEqual(gh.created(), [])

    def test_closed_recently_is_not_repeated(self):
        k = ea.card_key(card())
        gh = FakeGh([{"number": 1, "title": "x [erc:%s]" % k, "state": "CLOSED", "createdAt": "2026-11-12T12:00:00Z"}])
        self.assertEqual(ea.notify(payload(), payload(card()), gh=gh, now=NOW)["opened"], 0)

    def test_new_incident_days_later_alerts_again(self):
        k = ea.card_key(card())
        gh = FakeGh([{"number": 1, "title": "x [erc:%s]" % k, "state": "CLOSED", "createdAt": "2026-11-01T12:00:00Z"}])
        self.assertEqual(ea.notify(payload(), payload(card()), gh=gh, now=NOW)["opened"], 1)

    def test_two_new_cards_two_issues(self):
        gh = FakeGh()
        ea.notify(payload(), payload(card(), card(name="Leisure Centre")), gh=gh, now=NOW)
        self.assertEqual(len(gh.created()), 2)

    def test_gh_failure_never_raises(self):
        def boom(*a):
            raise RuntimeError("no network")
        self.assertEqual(ea.notify(payload(), payload(card()), gh=boom, now=NOW)["reason"], "error")


class OnlyRealMainRuns(unittest.TestCase):
    MAIN = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GH_TOKEN": "x",
            "GITHUB_WORKFLOW": "Incident rest centre watch", "GITHUB_REPOSITORY": "Postcode-economics/find-your-food-bank"}

    def test_main_watch_run_is_enabled(self):
        self.assertTrue(ea.enabled(ea.ROOT, dict(self.MAIN)))

    def test_everything_else_is_off(self):
        for change in ({"GITHUB_REF": "refs/pull/1/merge"}, {"GITHUB_REF": "refs/heads/fix/x"}, {"GH_TOKEN": ""},
                       {"GITHUB_ACTIONS": ""}, {"GITHUB_WORKFLOW": "tests"}, {"PYTEST_CURRENT_TEST": "t"},
                       {"GITHUB_REPOSITORY": "someone/fork"}):
            env = dict(self.MAIN, **change)
            self.assertFalse(ea.enabled(ea.ROOT, env), change)
        self.assertFalse(ea.enabled(tempfile.mkdtemp(), dict(self.MAIN)))

    def test_write_public_in_a_temp_folder_never_calls_github(self):
        import incident_rest_centre_live as live
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "overrides"))
        json.dump({"public": True}, open(os.path.join(d, "overrides", "incident_rest_centre_mode.json"), "w"))
        state = {"incidents": {"k": {"card": card()}}}
        with mock.patch.dict(os.environ, self.MAIN), mock.patch("subprocess.run", side_effect=AssertionError("gh called")):
            p = live.write_public(root=d, state=state, now=NOW)
        self.assertEqual(len(p["cards"]), 1)


class PublicFileIsTheRecord(unittest.TestCase):
    def setUp(self):
        import incident_rest_centre_live as live
        self.live = live
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "overrides"))
        json.dump({"public": True}, open(os.path.join(self.d, "overrides", "incident_rest_centre_mode.json"), "w"))

    def _public(self, *cards):
        json.dump({"public": True, "cards": list(cards), "councils": {}},
                  open(os.path.join(self.d, self.live.OUT_JSON), "w"))

    def test_refresh_without_state_keeps_the_live_rest_centre(self):
        self._public(card())
        self.live.sync_from_pages([], root=self.d, now=NOW)
        out = json.load(open(os.path.join(self.d, self.live.OUT_JSON)))
        self.assertEqual([c["name"] for c in out["cards"]], ["Civic Hall"])

    def test_old_private_state_cannot_bring_back_a_taken_down_card(self):
        self._public()
        stale = {"incidents": {"Exeter City Council|https://example.invalid/rest-centre": {"card": card()}}}
        self.live.save_state(stale, os.path.join(self.d, self.live.STATE))
        self.live.sync_from_pages([], root=self.d, now=NOW)
        out = json.load(open(os.path.join(self.d, self.live.OUT_JSON)))
        self.assertEqual(out["cards"], [])

    def test_expiry_still_applies(self):
        self._public(card(open_until="2026-11-12T10:00:00+00:00"))
        self.live.drop_expired(root=self.d, now=NOW)
        out = json.load(open(os.path.join(self.d, self.live.OUT_JSON)))
        self.assertEqual(out["cards"], [])


if __name__ == "__main__":
    unittest.main()
