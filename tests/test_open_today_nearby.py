"""Dean 26 Oct 2026, Littlehampton: Open today must not hide a nearby food bank that is closed today,
and the choice must not be saved for the next visit (it depends on the day)."""
import json, os, re, sys, unittest, threading, functools, http.server
sys.path.insert(0, os.path.dirname(__file__))
from site_ready import open_map
ROOT = os.path.join(os.path.dirname(__file__), "..")
LH = (50.8095, -0.5405)  # Littlehampton, same point as scripts/journeys.py

class Static(unittest.TestCase):
    def test_open_today_is_not_saved(self):
        h = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        self.assertIn("const f={walk:!!F.walk,vouch:!!F.vouch}", h)
        self.assertNotIn("localStorage.setItem('fbFilters',JSON.stringify({f:F}))", h)
        self.assertIn("['walk','vouch'].forEach", h)
    def test_closed_nearby_copy(self):
        h = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        self.assertIn("Filter on: open today,", h)
        self.assertIn("closed nearby hidden.", h)
        self.assertIn("Closed today, next open ", h)
        self.assertIn("box.id='otshut'", h)
    def test_approved_arun_places_and_bognor(self):
        raw = open(os.path.join(ROOT, "data.full.js"), encoding="utf-8").read()
        items = {i["id"]: i for i in json.loads(raw[raw.index("=") + 1:].rstrip().rstrip(";"))["items"]}
        pantry = items["st-peter-st-pauls-pantry"]
        self.assertEqual(pantry["address"], "Rustington Church Hall, BN16 3NR")
        self.assertEqual(pantry["postcode"], "BN16 3NR")
        self.assertFalse(pantry.get("phone"))
        self.assertEqual(pantry["opening_times"]["status"], "TIMES_TEXT_ONLY")
        self.assertEqual(pantry["opening_times"]["raw"], "Wednesdays, times vary")
        self.assertNotIn("structured", pantry["opening_times"])
        self.assertEqual(pantry["source_label"], "Arun District Council cost of living page")
        fridge = items["littlehampton-community-fridge"]
        self.assertTrue(fridge["venues_vary"])
        self.assertNotIn("lat", fridge)
        self.assertEqual(fridge["phone"], "0300 030 9376")
        self.assertEqual(fridge["tel"], "03000309376")
        self.assertEqual(fridge["phone_label"], "Fare Divide number")
        self.assertEqual(fridge["source_label"], pantry["source_label"])
        bog = items["bognor-regis"]
        self.assertIn("The Hope Centre, Saint Wilfrid Church, Ellasdale Road", bog["address"])
        self.assertEqual(bog["postcode"], "PO21 2SG")
        self.assertNotIn("Argyle", bog["address"])
        self.assertEqual(bog["phone"], "01243841275")
        approved = json.load(open(os.path.join(ROOT, "overrides", "foodbank_approved_new.json")))
        notes = json.load(open(os.path.join(ROOT, "overrides", "approved_new_places.json")))["foodbanks"]
        for i in ("st-peter-st-pauls-pantry", "littlehampton-community-fridge"):
            self.assertIn(i, approved); self.assertIn(i, notes)
        acc = open(os.path.join(ROOT, "access.js"), encoding="utf-8").read()
        self.assertIn('"st-peter-st-pauls-pantry":"walkin"', acc)

class Browser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa
        except Exception:
            raise unittest.SkipTest("playwright not installed")
        if not os.path.exists("/usr/bin/google-chrome"): raise unittest.SkipTest("no chrome")
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
        h.log_message = lambda *a: None
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()
    def test_littlehampton_monday_open_today(self):
        from playwright.sync_api import sync_playwright
        base = "http://127.0.0.1:%d/?nocount&testdate=2026-10-26" % self.srv.server_address[1]
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            c = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            pg = c.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
            open_map(pg, base); pg.wait_for_timeout(400)
            self.assertEqual(pg.evaluate("pageNow().getDay()"), 1)
            pg.click("#v3open"); pg.wait_for_timeout(300)
            self.assertFalse(pg.evaluate("!!(JSON.parse(localStorage.getItem('fbFilters')||'{\"f\":{}}').f.open)"))
            info = pg.evaluate("""([a,b])=>{nearest(a,b,'Littlehampton');
              const list=[...document.querySelectorAll('#list .card h3')].map(h=>h.textContent);
              const shut=document.getElementById('otshut');
              const line=(shut&&shut.querySelector('.otf'))?shut.querySelector('.otf').textContent:'';
              const card=[...shut.querySelectorAll('.otc')].find(x=>/Littlehampton & District Foodbank/.test(x.textContent));
              const n=(line.match(/(\\d+) closed nearby hidden/)||[])[1];
              return {list, line, next:card?card.querySelector('.otnext').textContent:'', n:n?+n:0,
                hidden:[...shut.querySelectorAll('.otc:not(.ota)')].length,
                fridge:[...shut.querySelectorAll('.ota')].map(x=>x.textContent).join(' | '),
                fridgeInList:list.some(t=>/Community Fridge/.test(t)),
                fridgeDir:!!(shut.querySelector('.ota a[href*="google.com/maps"]'))}}""", list(LH))
            self.assertNotIn("Littlehampton & District Foodbank", info["list"])
            self.assertIn("St Peter & St Paul's Pantry", info["list"])
            self.assertRegex(info["line"], r"Filter on: open today, \d+ closed nearby hidden")
            self.assertIn("Show all", info["line"])
            self.assertGreaterEqual(info["n"], 1)
            self.assertEqual(info["hidden"], info["n"])
            self.assertEqual(info["next"], "Closed today, next open Tue 1pm\u20133pm")
            self.assertIn("Venues vary", info["fridge"])
            self.assertIn("0300 030 9376", info["fridge"])
            self.assertIn("Fare Divide", info["fridge"])
            self.assertIn("Arun District Council cost of living page", info["fridge"])
            self.assertFalse(info["fridgeInList"])
            self.assertFalse(info["fridgeDir"])
            pg.click("#otshow"); pg.wait_for_timeout(400)
            back = pg.evaluate("[...document.querySelectorAll('#list .card h3')].map(h=>h.textContent)")
            self.assertIn("Littlehampton & District Foodbank", back)
            self.assertFalse(pg.evaluate("document.getElementById('openToday').checked"))
            self.assertIsNone(pg.evaluate("document.querySelector('#otshut .otf')"))
            pg.click("#v3open"); pg.wait_for_timeout(200)
            pan = pg.evaluate("""()=>{nearest(50.810862,-0.51025,'Rustington');
              const c=[...document.querySelectorAll('#list .card')].find(x=>/St Peter & St Paul/.test(x.textContent));
              return c?{t:c.textContent, voucher:/voucher needed/i.test(c.textContent)}:null}""")
            self.assertIsNotNone(pan)
            self.assertIn("Wednesdays, times vary", pan["t"])
            self.assertIn("Arun District Council cost of living page", pan["t"])
            self.assertFalse(pan["voucher"])
            self.assertEqual(errs, [])
            c.close(); b.close()
