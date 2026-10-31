"""10-minute incident rest centre watch: targeted rescan, no fetch without a warning, one alert."""
import datetime, json, os, shutil, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

NOW = datetime.datetime(2026, 10, 31, 6, 3, tzinfo=datetime.timezone.utc)
TEXT = "A rest centre has been opened at Riverside Hall because of flooding."
FAKE_GH = """#!/bin/bash
echo "$*" >> "$GH_CALLS"
case "$1 $2" in
  "issue list") echo '[]';;
  "label create") ;;
esac
exit 0
"""


class Watch(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        for sub in ("overrides", "logs", "reports", "bin"):
            os.makedirs(os.path.join(self.d, sub))
        json.dump({"public": True}, open(os.path.join(self.d, "overrides", "incident_rest_centre_mode.json"), "w"))
        gh = os.path.join(self.d, "bin", "gh")
        open(gh, "w").write(FAKE_GH)
        os.chmod(gh, 0o755)
        self.calls_path = os.path.join(self.d, "gh-calls")
        self._env = os.environ.copy()
        os.environ["PATH"] = os.path.join(self.d, "bin") + os.pathsep + os.environ["PATH"]
        os.environ["GH_CALLS"] = self.calls_path
        self.councils = [
            {"code": "ARU", "name": "Arun District Council", "nation": "England"},
            {"code": "OTH", "name": "Other Council", "nation": "England"},
        ]
        self.sources = [
            {"code": "ARU", "council": "Arun District Council", "news": "https://arun.example/news", "emergencies": "https://arun.example/emergencies"},
            {"code": "OTH", "council": "Other Council", "news": "https://other.example/news", "emergencies": None},
        ]
        self.swep = [{"code": "ARU", "council": "Arun District Council", "url": "https://arun.example/swep"}]

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        shutil.rmtree(self.d, ignore_errors=True)

    def gh_creates(self):
        if not os.path.exists(self.calls_path):
            return []
        return [l for l in open(self.calls_path).read().splitlines() if l.startswith("issue create")]

    def test_no_warning_fetches_nothing(self):
        import incident_rest_centre_watch as W
        seen = []
        out = W.run(root=self.d, warnings=[], fetcher=lambda u: seen.append(u), now=NOW,
                    councils=self.councils, sources=self.sources, swep_sources=self.swep)
        self.assertEqual(seen, [])
        self.assertEqual(out["fetched"], 0)
        self.assertEqual(out["opened"], 0)

    def test_ordinary_flood_warning_does_not_fetch(self):
        import incident_rest_centre_watch as W
        seen = []
        warnings = [{"level": "flood warning", "areas": ["Arun"], "title": "Flood warning", "source": "Environment Agency"}]
        W.run(root=self.d, warnings=warnings, fetcher=lambda u: seen.append(u) or {"http": 200, "html": TEXT}, now=NOW,
              councils=self.councils, sources=self.sources, swep_sources=self.swep)
        self.assertEqual(seen, [])

    def test_warning_rescans_that_council_and_switches_on(self):
        import incident_rest_centre_watch as W
        seen = []
        def fetcher(u):
            seen.append(u)
            if u.endswith("/news"):
                return {"http": 200, "html": TEXT}
            return {"http": 200, "html": "<p>Council information.</p>"}
        warnings = [{"level": "amber", "areas": ["Arun"], "title": "Amber warning of rain", "source": "Met Office"}]
        out = W.run(root=self.d, warnings=warnings, fetcher=fetcher, now=NOW,
                    councils=self.councils, sources=self.sources, swep_sources=self.swep)
        self.assertEqual(set(seen), {"https://arun.example/news", "https://arun.example/emergencies", "https://arun.example/swep"})
        self.assertNotIn("https://other.example/news", seen)
        self.assertEqual(out["opened"], 1)
        self.assertEqual(len(self.gh_creates()), 1)
        live = json.load(open(os.path.join(self.d, "incident_rest_centre_live.json")))
        self.assertEqual(len(live["cards"]), 1)
        self.assertEqual(live["cards"][0]["opened_for"], "flood")
        self.assertEqual(live["cards"][0]["name"], "Riverside Hall")
        self.assertTrue(str(live["cards"][0].get("last_checked", "")).startswith("Checked "))

    def test_warning_alone_does_not_make_a_card(self):
        import incident_rest_centre_watch as W
        warnings = [{"level": "red", "areas": ["Arun"], "title": "Severe flood warning", "source": "Environment Agency"}]
        out = W.run(root=self.d, warnings=warnings, fetcher=lambda u: {"http": 200, "html": "<p>Severe flood warning for Arun.</p>"},
                    now=NOW, councils=self.councils, sources=self.sources, swep_sources=self.swep)
        self.assertEqual(out["opened"], 0)
        self.assertEqual(self.gh_creates(), [])
        live = json.load(open(os.path.join(self.d, "incident_rest_centre_live.json")))
        self.assertEqual(live["cards"], [])

    def test_duplicate_find_from_both_loops_is_one_alert(self):
        import incident_rest_centre_switch_on as irso
        import incident_rest_centre_watch as W
        page = {"council": "Arun District Council", "url": "https://arun.example/news", "http": 200}
        off = dict(page, rest_centre=None)
        on = dict(page)
        irso.enrich_page(on, TEXT)
        irso.apply([off], [on], root=self.d, detected_at=NOW)
        self.assertEqual(len(self.gh_creates()), 1)
        W.run(root=self.d, warnings=[{"level": "red", "areas": ["Arun"], "title": "Red", "source": "Met Office"}],
              fetcher=lambda u: {"http": 200, "html": TEXT}, now=NOW,
              councils=self.councils, sources=self.sources, swep_sources=self.swep)
        self.assertEqual(len(self.gh_creates()), 1)

    def test_expired_card_comes_down_without_a_fetch_when_it_has_no_page(self):
        import incident_rest_centre_live as live
        import incident_rest_centre_watch as W
        state = {"incidents": {"k": {"council": "Arun District Council", "card": {
            "name": "Rest centre", "opened_by": "Arun District Council", "open_until": "2000-01-01T00:00:00+00:00"}}}}
        json.dump(state, open(os.path.join(self.d, "logs", "incident_rest_centre_live_state.json"), "w"))
        seen = []
        W.run(root=self.d, warnings=[], fetcher=lambda u: seen.append(u), now=NOW,
              councils=self.councils, sources=self.sources, swep_sources=self.swep)
        self.assertEqual(seen, [])
        left = live.load_state(os.path.join(self.d, live.STATE))
        self.assertEqual(left.get("incidents"), {})


class Workflow(unittest.TestCase):
    def test_schedule_and_single_alert(self):
        text = open(os.path.join(ROOT, ".github", "workflows", "incident-rest-centre-watch.yml"), encoding="utf-8").read()
        self.assertIn("name: Incident rest centre watch (every 10 min)", text)
        self.assertIn('cron: "*/10 * * * *"', text)
        self.assertIn("group: incident-rest-centre-watch", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertEqual(text.count("alert.py open incident-watch"), 1)
        self.assertIn("python scripts/incident_rest_centre_watch.py", text)
        self.assertNotIn("playwright", text)
        shelters = open(os.path.join(ROOT, ".github", "workflows", "refresh-shelters.yml"), encoding="utf-8").read()
        self.assertIn("Council-area browser test", shelters)
        self.assertIn("playwright==1.47.0", shelters)
        daily = open(os.path.join(ROOT, ".github", "workflows", "swep-daily.yml"), encoding="utf-8").read()
        self.assertIn("continue-on-error: true", daily[daily.index("id: full"):daily.index("Commit logs")])
        self.assertIn("::error::", daily)


class Wording(unittest.TestCase):
    def test_evacuation_notice_is_a_short_phrase_and_a_clean_place(self):
        import weather as w
        import alert
        text = "A rest centre has been opened for those who have had to evacuate their properties"
        rec = w.parse_announcement(text, "Test Council", "https://example.gov.uk/news", NOW)
        self.assertEqual(rec["name"], "Rest centre")
        self.assertEqual(rec["opened_for"], "evacuation")
        lead = "Rest centre open: Test Council has opened a rest centre for people affected by %s." % rec["opened_for"]
        self.assertNotIn("prop", lead)
        self.assertNotIn("those who", rec["name"])
        title = alert.switch_on_title("Test Council", rec["name"], "Rest centres (incidents)")
        self.assertIn("Rest centre", title)
        self.assertNotIn("prop", title)
        self.assertNotRegex(title, r"by t$")

    def test_checked_time_is_uk(self):
        import weather as w
        self.assertEqual(w.fmt_checked(NOW), "Checked 6:03am, Sat 31 Oct")

    def test_finish_exits_when_the_alert_fails(self):
        import swep
        with self.assertRaises(SystemExit) as cm:
            swep.finish({"alert_error": "AlertError: gh issue create failed"})
        self.assertEqual(cm.exception.code, 1)


class Sources(unittest.TestCase):
    def test_choose_news_and_emergencies_not_an_old_story(self):
        import rest_centre_sources as S
        base = "https://example.gov.uk/"
        links = [
            ("https://example.gov.uk/news", "News"),
            ("https://example.gov.uk/news/2019/rest-centre-closed", "Rest centre closed"),
            ("https://example.gov.uk/emergencies", "Emergencies"),
            ("https://example.gov.uk/planning-applications", "Planning applications"),
            ("https://other.example/news", "News"),
        ]
        got = S.choose_pages(base, links)
        self.assertEqual(got["news"], "https://example.gov.uk/news")
        self.assertEqual(got["emergencies"], "https://example.gov.uk/emergencies")

    def test_discover_records_unresolved_instead_of_guessing(self):
        import rest_centre_sources as S
        pages = {
            "https://ok.example/": {"http": 200, "url": "https://ok.example/", "html": '<a href="/news">News</a><a href="/emergencies">Emergencies</a>'},
            "https://ok.example/news": {"http": 200, "url": "https://ok.example/news", "html": "<p>News</p>"},
            "https://ok.example/emergencies": {"http": 200, "url": "https://ok.example/emergencies", "html": "<p>Emergencies</p>"},
            "https://down.example/": {"http": 403, "url": "https://down.example/", "html": ""},
        }
        councils = [
            {"code": "OK", "name": "Ok Council", "nation": "England", "site": "https://ok.example/"},
            {"code": "DN", "name": "Down Council", "nation": "England", "site": "https://down.example/"},
        ]
        out = os.path.join(self.d if hasattr(self, "d") else tempfile.mkdtemp(), "src.json")
        # discover writes next to out_path's sibling report; use a temp dir
        d = tempfile.mkdtemp()
        try:
            payload = S.discover(councils, fetcher=lambda u: pages.get(u, {"http": 404, "url": u, "html": ""}),
                                 out_path=os.path.join(d, "src.json"), report_path=os.path.join(d, "report.md"), threads=1)
        finally:
            pass
        by = {c["code"]: c for c in payload["councils"]}
        self.assertEqual(by["OK"]["news"], "https://ok.example/news")
        self.assertIsNone(by["DN"]["news"])
        self.assertEqual(payload["unresolved"][0]["code"], "DN")
        self.assertNotIn("/news", json.dumps(payload["unresolved"]))
        shutil.rmtree(d, ignore_errors=True)


class Coverage(unittest.TestCase):
    def test_every_council_is_listed(self):
        sweep = json.load(open(os.path.join(ROOT, "scripts", "sweep_sources.json"), encoding="utf-8"))["councils"]
        src = json.load(open(os.path.join(ROOT, "overrides", "rest_centre_sources.json"), encoding="utf-8"))
        self.assertEqual({c["code"] for c in sweep}, {c["code"] for c in src["councils"]})
        for c in src["councils"]:
            for key in ("news", "emergencies"):
                if c.get(key):
                    self.assertTrue(c[key].startswith("http"), c["code"])


class Pages(unittest.TestCase):
    def test_approved_wording(self):
        faq = open(os.path.join(ROOT, "faq.html"), encoding="utf-8").read()
        terms = open(os.path.join(ROOT, "terms.html"), encoding="utf-8").read()
        privacy = open(os.path.join(ROOT, "privacy.html"), encoding="utf-8").read()
        q = "What is a rest centre alert?"
        a = ("When a council opens a rest centre for people affected by an incident such as a flood, fire, gas leak or evacuation, "
             "we show it on the map with a red banner. We only show it to people searching a postcode in that council's area, "
             "and only when the council has said so on its own website. It comes down when the council removes it, or after 24 hours "
             "unless the council confirms it's still open. We check council pages regularly, but we might miss one or be a little behind, "
             "so always follow official advice. If you or anyone else is in danger, call")
        self.assertIn(q, faq)
        self.assertLess(faq.index("Severe weather:"), faq.index(q))
        self.assertIn(a, faq)
        self.assertIn("<h2>Rest centre alerts</h2>", terms)
        self.assertIn("Rest centre alerts repeat what councils publish on their own websites.", terms)
        self.assertIn("The same postcodes.io lookup also tells us which council area you're in.", privacy)
        self.assertLess(privacy.index("sent to postcodes.io to find its location."), privacy.index("which council area you're in"))
        self.assertIn("Beth yw rhybudd canolfan orffwys?", faq)

    def test_terminated_postcode_asks_for_the_council_area(self):
        html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        i = html.index("if(r.terminated&&r.terminated.latitude)")
        window = html[i:i + 700]
        self.assertIn("terminated_postcodes/", window)
        self.assertIn("admin_district", window)
        self.assertNotIn("localStorage.setItem('lad'", html)


if __name__ == "__main__":
    unittest.main()
