"""Phone QA fixes from the 28 Oct 2026 live check (B1, B2, B4, B6, B7).

Runs in Chromium (google-chrome, phone emulation) and in WebKit as an iPhone when installed.
postcodes.io is answered by a route stub, map tiles are stubbed, so no real network is used.
"""
import json, mimetypes, os, sys, unittest
sys.path.insert(0, os.path.dirname(__file__))
from site_ready import READY
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
import check_browser as CB
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BASE = "https://helpmap.uk"
OFM_STYLE = ('{"version":8,"sources":{"uk":{"type":"geojson","data":{"type":"Feature","properties":{},"geometry":'
             '{"type":"Polygon","coordinates":[[[-11,49],[3,49],[3,61],[-11,61],[-11,49]]]}}}},"layers":['
             '{"id":"background","type":"background","paint":{"background-color":"#f2f3f0"}},'
             '{"id":"land","type":"fill","source":"uk","paint":{"fill-color":"#a8d08d"}}]}')
MAN = {"postcode": "M1 1AE", "latitude": 53.4808, "longitude": -2.2426}


def until(pg, js, secs=25):
    """Poll with evaluate (the site's CSP blocks wait_for_function's eval in WebKit)."""
    for _ in range(secs * 4):
        try:
            if pg.evaluate(js):
                return True
        except Exception:
            pass
        pg.wait_for_timeout(250)
    raise AssertionError("timed out: " + js)


def pc_stub(route):
    u = route.request.url
    if "/postcodes/M1%201AE" in u:
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({"status": 200, "result": MAN}))
    if "/places" in u:
        return route.fulfill(status=200, content_type="application/json", body=json.dumps({"status": 200, "result": []}))
    return route.fulfill(status=404, content_type="application/json", body=json.dumps({"status": 404, "error": "Invalid postcode"}))


class PhoneQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright  # noqa
        except Exception:
            raise unittest.SkipTest("playwright not installed")
        cls.base = BASE + "/?fresh=1"

    def engines(self):
        """Chromium phone (normal map), iPhone WebKit with the backup map off, and with it forced on."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ran = 0
            for name in ("chromium", "webkit", "webkit-backup"):
                try:
                    if name == "chromium":
                        if not os.path.exists("/usr/bin/google-chrome"):
                            continue
                        b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
                        opts = dict(viewport={"width": 375, "height": 812}, device_scale_factor=2, has_touch=True, is_mobile=True)
                    else:
                        b = p.webkit.launch()
                        opts = dict(p.devices["iPhone 13"]); opts["viewport"] = {"width": 375, "height": 812}
                except Exception:
                    continue
                ran += 1
                self.backup = name.endswith("backup")
                try:
                    yield name, b, opts
                finally:
                    b.close()
            if not ran:
                raise unittest.SkipTest("no browser")

    def page(self, b, opts, light=False):
        c = b.new_context(service_workers="block", **opts)
        backup = self.backup

        def local(route):
            path = route.request.url.split(BASE, 1)[1].split("?")[0].split("#")[0] or "/"
            f = os.path.join(ROOT, path.lstrip("/"))
            f = os.path.join(f, "index.html") if os.path.isdir(f) else f
            if not os.path.isfile(f):
                return route.fulfill(status=404, body="")
            with open(f, "rb") as fh:
                body = fh.read()
            route.fulfill(status=200, body=body, headers={"content-type": mimetypes.guess_type(f)[0] or "text/html", "cache-control": "no-store"})

        def tiles(route):
            url = route.request.url
            h = {"access-control-allow-origin": "*"}
            if "tiles.openfreemap.org" in url:
                if "/styles/" in url:
                    return route.fulfill(status=200, content_type="application/json", body=OFM_STYLE, headers=h)
                return route.fulfill(status=404, body="", headers=h)
            return route.fulfill(status=403 if backup else 200, content_type="image/png", body=CB.TILE_PNG, headers=h)

        c.route("**/*", lambda r: r.abort())          # nothing real leaves the browser
        c.route("https://*.tile.openstreetmap.org/**", tiles)
        c.route("https://tile.openstreetmap.org/**", tiles)
        c.route("https://tiles.openfreemap.org/**", tiles)
        c.route("https://api.postcodes.io/**", pc_stub)
        c.route(BASE + "/**", local)
        pg = c.new_page()
        pg.goto(self.base, wait_until="domcontentloaded")
        until(pg, READY, 40)
        pg.wait_for_timeout(1200)
        if light != pg.evaluate("document.documentElement.classList.contains('light')"):
            pg.click("#v3light"); pg.wait_for_timeout(300)
        return c, pg

    def search(self, pg, q):
        pg.fill("#q", q); pg.press("#q", "Enter"); pg.wait_for_timeout(2500)

    def test_b1_nearest_list_follows_type(self):
        for name, b, opts in self.engines():
            for k, cls_ in (("sh", "xsh"), ("ws", "xws")):
                c, pg = self.page(b, opts)
                pg.click(f".v3b[data-l={k}]"); pg.wait_for_timeout(1500)
                self.search(pg, "M1 1AE")
                until(pg, f"document.querySelectorAll('#xlist .card.{cls_}').length>0")
                r = pg.evaluate(f"""()=>({{fb:[...document.querySelectorAll('#list .card,#otshut .otc')].filter(e=>e.getClientRects().length).length,
                    x:[...document.querySelectorAll('#xlist .card.{cls_}')].filter(e=>e.getClientRects().length).length,
                    heads:[...document.querySelectorAll('.lh')].filter(e=>e.getClientRects().length).map(e=>e.textContent)}})""")
                self.assertEqual(r["fb"], 0, (name, k, r))
                self.assertGreater(r["x"], 0, (name, k, r))
                self.assertFalse(any(h.startswith("Nearest 5 to") for h in r["heads"]), (name, k, r))
                # back to food bank: the food bank list returns
                pg.click(".v3b[data-l=fb]"); pg.wait_for_timeout(1500)
                n = pg.evaluate("[...document.querySelectorAll('#list .card')].filter(e=>e.getClientRects().length).length")
                self.assertGreater(n, 0, (name, k))
                c.close()

    def test_b2_bad_postcode_clears_results_and_says_so(self):
        for name, b, opts in self.engines():
            c, pg = self.page(b, opts, light=True)
            self.search(pg, "M1 1AE")
            self.assertGreater(pg.evaluate("document.querySelectorAll('#list .card').length"), 0)
            self.search(pg, "ZZ99 9ZZ")
            pg.wait_for_timeout(500)
            r = pg.evaluate("""()=>({cards:document.querySelectorAll('#list .card,#xlist .card').length,
                pill:document.getElementById('v3pill').innerText, alert:!!document.querySelector('#v3pill .v3err[role=alert]'),
                saved:localStorage.getItem('lastSearch')})""")
            self.assertEqual(r["cards"], 0, (name, r))
            self.assertIn("Postcode not found", r["pill"], (name, r))
            self.assertIn("ZZ99 9ZZ", r["pill"], (name, r))
            self.assertNotIn("near M1", r["pill"], (name, r))
            self.assertTrue(r["alert"], (name, r))
            self.assertIsNone(r["saved"], (name, r))
            # a type tap after the failure does not bring the old place back
            pg.click(".v3b[data-l=ws]"); pg.wait_for_timeout(1500)
            self.assertEqual(pg.evaluate("document.querySelectorAll('#list .card,#xlist .card').length"), 0, name)
            # and a good search afterwards works again
            pg.click(".v3b[data-l=fb]"); pg.wait_for_timeout(500)
            self.search(pg, "M1 1AE")
            self.assertGreater(pg.evaluate("document.querySelectorAll('#list .card').length"), 0, name)
            self.assertIn("M1 1AE", pg.inner_text("#v3pill"), name)
            c.close()

    def test_b4_filter_close_not_alone_at_375_dark(self):
        for name, b, opts in self.engines():
            c, pg = self.page(b, opts)
            self.assertFalse(pg.evaluate("document.documentElement.classList.contains('light')"))
            r = pg.evaluate("""()=>{const g=id=>document.getElementById(id).getBoundingClientRect();const x=g('fhide'),o=g('v3open'),t=g('v3tools'),
                chips=[...document.querySelectorAll('#v3filt .fchip[data-f]')].map(e=>e.getBoundingClientRect());
                return {xy:x.top,oy:o.top,ty:t.top,cy:chips.map(c=>c.top),xr:x.right,ow:o.width,oh:o.height,vw:innerWidth,
                  sw:document.documentElement.scrollWidth}}""")
            rowmates = [y for y in r["cy"] + [r["oy"], r["ty"]] if abs(y - r["xy"]) < 4]
            self.assertTrue(rowmates, (name, r))             # the ✕ shares its row with a chip or Open today
            self.assertLess(r["oh"], 50, (name, r))           # 'Open today only' on one line
            self.assertLessEqual(r["xr"], r["vw"], (name, r))
            self.assertLessEqual(r["sw"], r["vw"], (name, r))
            c.close()

    def test_b6_tap_targets(self):
        for name, b, opts in self.engines():
            c, pg = self.page(b, opts)
            self.search(pg, "M1 1AE")
            pg.evaluate("document.getElementById('map').scrollIntoView({block:'center'})"); pg.wait_for_timeout(800)
            r = pg.evaluate("""()=>{const out={small:[],pins:[],stolen:[]};
              const sel='footer a,.legal a,.fresh a,#xupd a,#list .card a:not(.btn),a.v3pl';
              document.querySelectorAll(sel).forEach(a=>{const rs=[...a.getClientRects()];if(!rs.length)return;const h=Math.max(...rs.map(x=>x.height));if(h<44)out.small.push([a.textContent.trim().slice(0,30),h])});
              const mapR=document.getElementById('map').getBoundingClientRect();
              const pins=[...document.querySelectorAll('.leaflet-marker-icon.pin')].filter(p=>{const b=p.getBoundingClientRect();return b.top>mapR.top+8&&b.bottom<mapR.bottom-8&&b.left>mapR.left+8&&b.right<mapR.right-8});
              pins.slice(0,5).forEach(p=>{const b=p.getBoundingClientRect();
                [[b.left+2,b.top+b.height/2],[b.right-2,b.top+b.height/2],[b.left+b.width/2,b.top+2],[b.left+b.width/2,b.bottom-2]].forEach(([x,y])=>{const e=document.elementFromPoint(x,y);if(!(e&&(e===p||p.contains(e)||e.closest('.leaflet-marker-icon'))))out.pins.push([Math.round(x),Math.round(y),e&&e.className])})});
              out.npins=pins.length;
              document.querySelectorAll('button,.btn,summary,input,select').forEach(e=>{const b=e.getBoundingClientRect();if(!b.width||b.top<0||b.bottom>innerHeight)return;
                const cx=b.left+b.width/2,cy=b.top+b.height/2,h=document.elementFromPoint(cx,cy);if(h&&!e.contains(h)&&h.closest('a')&&!e.contains(h.closest('a'))&&!h.closest('a').contains(e))out.stolen.push([e.id||e.className,h.closest('a').textContent.slice(0,20)])});
              return out}""")
            self.assertEqual(r["small"], [], (name, r["small"]))
            self.assertGreater(r["npins"], 0, name)
            self.assertEqual(r["pins"], [], (name, r["pins"]))
            self.assertEqual(r["stolen"], [], (name, r["stolen"]))
            c.close()

    def test_b7_tel_links_have_names(self):
        for name, b, opts in self.engines():
            c, pg = self.page(b, opts)
            pg.click(".v3b[data-l=sh]"); pg.wait_for_timeout(1500)
            self.search(pg, "M1 1AE")
            until(pg, "document.querySelectorAll('#xlist .card.xsh').length>0")
            bad = pg.evaluate("""()=>[...document.querySelectorAll('a[href^="tel:"]')].filter(a=>!(a.textContent.trim()||'').length&&!(a.getAttribute('aria-label')||'').trim()).map(a=>a.outerHTML.slice(0,120))""")
            self.assertEqual(bad, [], name)
            # helplines inside the folded 'More free helplines' list carry a label, and show their number once opened
            r = pg.evaluate("""()=>{const d=document.querySelector('#v3sos details.hlp');if(!d)return null;d.open=true;
                return [...d.querySelectorAll('a[href^="tel:"]')].filter(a=>a.getClientRects().length).map(a=>[a.getAttribute('aria-label'),a.innerText.trim()])}""")
            self.assertTrue(r, name)
            for lab, txt in r:
                self.assertTrue(lab and lab.startswith("Call "), (name, lab))
                self.assertTrue(txt, (name, lab))
            c.close()


if __name__ == "__main__":
    unittest.main()
