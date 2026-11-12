"""Live incident rest centres: public mode, LAD gate, SWEP/warm spaces excluded from the live file."""
import json, os, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class LiveFile(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, "overrides"))
        os.makedirs(os.path.join(self.d, "logs"))
        json.dump({"public": True}, open(os.path.join(self.d, "overrides", "incident_rest_centre_mode.json"), "w"))

    def test_public_true_written_to_live_json(self):
        import incident_rest_centre_live as live

        payload = live.write_public(root=self.d, state={"incidents": {}}, now=__import__("datetime").datetime(2026, 10, 30, tzinfo=__import__("datetime").timezone.utc))
        self.assertTrue(payload["public"])
        on_disk = json.load(open(os.path.join(self.d, live.OUT_JSON)))
        self.assertTrue(on_disk["public"])
        self.assertEqual(on_disk["category"], "incident_rest_centre")

    def test_public_false_hides_even_with_cards_in_state(self):
        import incident_rest_centre_live as live

        json.dump({"public": False}, open(os.path.join(self.d, "overrides", "incident_rest_centre_mode.json"), "w"))
        card = {"id": "x", "name": "Hall", "live": True, "lad": "E07000223", "category": "incident_rest_centre",
                "open_until": "2099-01-01T12:00:00+00:00"}
        state = {"incidents": {"k": {"card": card}}}
        payload = live.write_public(root=self.d, state=state)
        self.assertFalse(payload["public"])
        self.assertEqual(payload["cards"], [])

    def test_sync_never_puts_swep_in_live_cards(self):
        import incident_rest_centre_live as live

        pages = [{
            "council": "Test Council",
            "url": "https://example.gov.uk/swep",
            "status": "active",
            "_text": "SWEP is active tonight.",
            "rest_centre": None,
        }]
        n = live.sync_from_pages(pages, root=self.d)
        self.assertEqual(n, 0)
        payload = json.load(open(os.path.join(self.d, live.OUT_JSON)))
        self.assertEqual(payload["cards"], [])

    def test_sync_incident_rest_centre_only_category(self):
        import incident_rest_centre_live as live

        text = "Flooding: a rest centre has been opened at Riverside Hall BN17 5AA for residents."
        pages = [{
            "council": "Arun District Council",
            "url": "https://example.gov.uk/flood",
            "_text": text,
            "rest_centre": {"active": True, "name": "Riverside Hall", "quote": text, "location": "BN17 5AA"},
        }]
        with mock.patch.object(live, "_geocode_postcode", return_value=(50.81, -0.54)):
            with mock.patch("council_lad.lad_for_council", return_value="E07000224"):
                n = live.sync_from_pages(pages, root=self.d)
        self.assertEqual(n, 1)
        payload = json.load(open(os.path.join(self.d, live.OUT_JSON)))
        self.assertEqual(len(payload["cards"]), 1)
        self.assertEqual(payload["cards"][0].get("category"), "incident_rest_centre")
        self.assertNotIn("swep_badge", payload["cards"][0])
        raw = open(os.path.join(self.d, live.OUT_JSON)).read().lower()
        self.assertNotIn("warm space", raw)
        self.assertNotIn("warmspaces", raw)

    def test_sync_keeps_previous_district_when_rebuild_has_none(self):
        import incident_rest_centre_live as live

        text = "The council has opened a rest centre at TEST — do not travel for people affected by a flood."
        pages = [{
            "council": "Arun District Council",
            "url": "https://example.gov.uk/test-rest-centre",
            "_text": text,
            "rest_centre": {"active": True, "name": "TEST — do not travel", "quote": text, "location": ""},
        }]
        with mock.patch.object(live, "_geocode_postcode", return_value=(None, None)):
            with mock.patch("council_lad.lad_for_council", return_value="E07000224"):
                live.sync_from_pages(pages, root=self.d)
            with mock.patch("council_lad.lad_for_council", return_value=None):
                n = live.sync_from_pages(pages, root=self.d)
        self.assertEqual(n, 1)
        card = json.load(open(os.path.join(self.d, live.OUT_JSON)))["cards"][0]
        self.assertEqual(card.get("lad"), "E07000224")
        self.assertIsNone(card.get("lat"))
        self.assertIsNone(card.get("lng"))



class LiveCouncilGate(unittest.TestCase):
    """Browser: live mode with public:true still gates banner/pins by visitor LAD."""

    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            raise unittest.SkipTest("playwright not available")
        if not os.path.exists("/usr/bin/google-chrome"):
            raise unittest.SkipTest("no chrome")
        import functools, http.server, threading

        cls._live = os.path.join(ROOT, "incident_rest_centre_live.json")
        cls._mode = os.path.join(ROOT, "overrides", "incident_rest_centre_mode.json")
        cls._saved_live = open(cls._live, encoding="utf-8").read() if os.path.exists(cls._live) else None
        cls._saved_mode = open(cls._mode, encoding="utf-8").read() if os.path.exists(cls._mode) else None
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
        h.log_message = lambda *a: None
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch(executable_path="/usr/bin/google-chrome")

    @classmethod
    def tearDownClass(cls):
        if cls._saved_live is not None:
            open(cls._live, "w", encoding="utf-8").write(cls._saved_live)
        if cls._saved_mode is not None:
            open(cls._mode, "w", encoding="utf-8").write(cls._saved_mode)
        if getattr(cls, "browser", None):
            cls.browser.close()
        if getattr(cls, "_pw", None):
            cls._pw.stop()
        if getattr(cls, "srv", None):
            cls.srv.shutdown()

    def _write_live(self, cards, public=True):
        json.dump(
            {"public": public, "generated": "2026-10-30T12:00:00+00:00", "category": "incident_rest_centre", "cards": cards, "councils": {}},
            open(self._live, "w"),
            ensure_ascii=False,
        )
        json.dump({"public": public}, open(self._mode, "w"))

    def test_public_true_empty_cards_no_live_ui(self):
        self._write_live([], public=True)
        ctx = self.browser.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page()
        pg.goto(self.base + "/?fresh=1&nocount=1", wait_until="load")
        pg.wait_for_timeout(2500)
        self.assertNotIn("em-live", pg.evaluate("document.documentElement.className"))
        self.assertEqual(pg.locator("#em-banner").count(), 0)
        ctx.close()

    def test_visitor_outside_lad_sees_no_banner(self):
        card = {
            "id": "arun-hall",
            "name": "Riverside Hall",
            "live": True,
            "lad": "E07000224",
            "lat": 50.81,
            "lng": -0.54,
            "open_until": "2099-01-01T12:00:00+00:00",
            "open_until_label": "open",
            "opened_by": "Arun District Council",
            "opened_for": "flooding",
            "category": "incident_rest_centre",
        }
        self._write_live([card], public=True)
        ctx = self.browser.new_context(viewport={"width": 390, "height": 844})
        ctx.add_init_script("window.__visitorLad='E09000003';")  # Westminster, not Arun
        pg = ctx.new_page()
        pg.goto(self.base + "/?fresh=1&nocount=1", wait_until="load")
        pg.wait_for_timeout(3500)
        self.assertIn("em-live", pg.evaluate("document.documentElement.className"))
        self.assertTrue(pg.evaluate("document.getElementById('em-banner').hidden"))
        self.assertEqual(pg.locator("#em-root .em-card").count(), 0)
        ctx.close()

    def test_note_above_map_and_card_survive_type_switches(self):
        """12 Nov 2026 (Dean): one compact note just above the map (not in the header); the rest centre card sits first,
        above the list; switching Food bank / Warm space / Shelter keeps the note, the card and the red pin."""
        card = {"id": "rc-switch", "name": "Riverside Hall", "live": True, "lad": "E07000224", "lat": 50.81, "lng": -0.54,
                "open_until": "2099-01-01T12:00:00+00:00", "open_until_label": "open", "opened_by": "Example District Council",
                "opened_for": "flooding", "source_url": "https://example.gov.uk/page", "category": "incident_rest_centre"}
        self._write_live([card], public=True)
        ctx = self.browser.new_context(viewport={"width": 390, "height": 844})
        ctx.add_init_script("window.__visitorLad='E07000224';")
        pg = ctx.new_page()
        pg.goto(self.base + "/?fresh=1&nocount=1", wait_until="load")
        pg.wait_for_selector("#em-banner .em-cta", timeout=15000)
        pg.wait_for_selector(".em-pinwrap", timeout=15000)
        pos = pg.evaluate("""()=>{const b=document.getElementById('em-banner'),m=document.getElementById('map'),r=document.getElementById('em-root'),l=document.getElementById('list');
          return {inHeader:!!b.closest('header'),beforeMap:!!(b.compareDocumentPosition(m)&Node.DOCUMENT_POSITION_FOLLOWING),
            rootBeforeList:!l.contains(r)&&!!(r.compareDocumentPosition(l)&Node.DOCUMENT_POSITION_FOLLOWING),noPopup:!document.querySelector('.leaflet-popup')}}""")
        self.assertEqual(pos, {"inHeader": False, "beforeMap": True, "rootBeforeList": True, "noPopup": True})
        vis = """()=>{const b=document.getElementById('em-banner'),c=document.querySelector('#em-root .em-card');
          return [!!b&&!b.hidden&&b.getClientRects().length>0,!!c&&!c.hidden&&c.getClientRects().length>0,document.querySelectorAll('.em-pinwrap').length]}"""
        for label in ("Shelter", "Warm space", "Food bank"):
            btn = pg.locator(".v3b", has_text=label).first
            if not btn.count():
                continue
            btn.click()
            pg.wait_for_timeout(800)
            self.assertEqual(pg.evaluate(vis), [True, True, 1], label)
        ctx.close()

    def test_visitor_inside_lad_sees_banner(self):
        card = {
            "id": "arun-hall",
            "name": "Riverside Hall",
            "live": True,
            "lad": "E07000224",
            "lat": 50.81,
            "lng": -0.54,
            "open_until": "2099-01-01T12:00:00+00:00",
            "open_until_label": "open",
            "opened_by": "Arun District Council",
            "opened_for": "flooding",
            "source_url": "https://example.gov.uk/page",
            "checked_at": "2026-10-31T06:03:00+00:00",
            "category": "incident_rest_centre",
        }
        self._write_live([card], public=True)
        ctx = self.browser.new_context(viewport={"width": 390, "height": 844})
        ctx.add_init_script("window.__visitorLad='E07000224';")
        pg = ctx.new_page()
        pg.goto(self.base + "/?fresh=1&nocount=1", wait_until="load")
        pg.wait_for_selector("#em-banner .em-cta", timeout=15000)
        self.assertFalse(pg.evaluate("document.getElementById('em-banner').hidden"))
        banner = pg.locator("#em-banner").inner_text()
        self.assertIn("Rest centre open near you: ", banner)
        self.assertIn("Tap for details", banner)
        card = pg.locator("#em-root .em-card").inner_text()  # 12 Nov 2026: the full wording moved from the banner to the card
        self.assertIn("Checked 6:03am, Sat 31 Oct", card)
        self.assertNotIn("2026-10-31T06:03", card)
        self.assertIn("call 999", card)
        self.assertEqual(pg.locator("#em-root .em-card").count(), 1)
        ctx.close()


if __name__ == "__main__":
    unittest.main()
