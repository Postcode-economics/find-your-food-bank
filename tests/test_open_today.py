"""Open today (Dean, 25 Oct 2026): the control stays tappable with Warm spaces or Shelters selected,
and it hides warm spaces / shelters listed as closed today (places with no times stay listed)."""
import os, json, sys, unittest, threading, functools, http.server
sys.path.insert(0, os.path.dirname(__file__))
from site_ready import open_map
ROOT = os.path.join(os.path.dirname(__file__), "..")
V3 = open(os.path.join(ROOT, "v3.js"), encoding="utf-8").read()
LJ = open(os.path.join(ROOT, "layers.js"), encoding="utf-8").read()

class Static(unittest.TestCase):
    def test_open_not_dimmed(self):
        self.assertIn("document.querySelectorAll('#chips [data-f]').forEach(e=>{e.classList.toggle('v3off'", V3)  # only fb-only chips dim (25 Oct live bug: ✕ was inert)
        self.assertNotIn("'v3open'].forEach", V3)
    def test_layers_follow_open_today(self):
        self.assertIn("shutToday", V3); self.assertIn("ot&&(i.ended||V3.shutToday(k,i))", LJ)

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
    def test_tap_and_filter(self):
        from playwright.sync_api import sync_playwright
        base = f"http://127.0.0.1:{self.srv.server_address[1]}/?fresh=1"
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
            for w in (390, 1366):
                for k in ("ws", "sh", "fb"):
                    c = b.new_context(viewport={"width": w, "height": 844}, service_workers="block")
                    pg = c.new_page(); open_map(pg, base); pg.wait_for_timeout(1500)
                    pg.click(f".v3b[data-l={k}]"); pg.wait_for_timeout(800)
                    pg.click("#v3open", timeout=3000)   # a real tap on the visible chip
                    pg.wait_for_timeout(300)
                    self.assertTrue(pg.evaluate("document.getElementById('openToday').checked"), (w, k))
                    c.close()
            # filtering: every listed warm space / shelter is open today or has no times
            c = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            pg = c.new_page(); open_map(pg, base); pg.wait_for_timeout(1500)
            pg.click(".v3b[data-l=ws]"); pg.wait_for_timeout(800); pg.click("#v3open"); pg.wait_for_timeout(300)
            for lat, lng in ((51.5074, -0.1278), (53.4808, -2.2426), (55.9533, -3.1883), (50.8095, -0.5405)):
                bad = pg.evaluate("""([a,b])=>{nearest(a,b,'test');const out=[];let n=0;for(const [k,D] of [['ws',window.WARMSPACES],['sh',window.SHELTERS]]){if(!D)continue;
                  const names=[...document.querySelectorAll('#xlist .card.x'+k+' h3')].map(h=>h.textContent);n+=names.length;
                  D.items.filter(i=>names.includes(i.name)).forEach(i=>{if(i.ended||V3.shutToday(k,i))out.push(i.name)})}return n?out:['no cards']}""", [lat, lng])
                self.assertEqual(bad, [], (lat, lng))
            c.close()
            # note: hidden when off, shown with the exact text when on
            c = b.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            pg = c.new_page(); open_map(pg, base); pg.wait_for_timeout(1500)
            vis = lambda: pg.evaluate("()=>{const e=document.querySelector('.tnote');return !e.hidden&&e.offsetParent!==null}")
            self.assertFalse(vis())
            pg.click("#v3open"); pg.wait_for_timeout(300)
            self.assertTrue(vis()); self.assertEqual(pg.evaluate("document.querySelector('.tnote').textContent"), "Showing places open today. If no times are listed, call before you go.")
            pg.click("#v3open"); pg.wait_for_timeout(300); self.assertFalse(vis())
            # Dean 25 Oct 09:37: Open today ON = places closed today hidden (no-times stay), strictly nearest first (every layer)
            pg.click("#v3open")
            for sel in ("ws", "sh"):
              pg.click(f".v3b[data-l={sel}]"); pg.wait_for_timeout(1000)
              for lat, lng in ((51.5074, -0.1278), (53.4808, -2.2426), (50.8095, -0.5405)):
                  r = pg.evaluate("""([a,b])=>{nearest(a,b,'test');const out={};
                    out.fb=[...document.querySelectorAll('#list .card')].map(c=>{const i=items[+c.dataset.k];return [openToday(i)?0:closedToday(i)?2:1,dists[+c.dataset.k]]});
                    for(const [k,D] of [['ws',window.WARMSPACES],['sh',window.SHELTERS]]){if(!D)continue;
                      out[k]=[...document.querySelectorAll('#xlist .card.x'+k+' h3')].map(h=>{const i=D.items.find(x=>x.name===h.textContent);return [V3.openTodayL(k,i)?0:(i.ended||V3.shutToday(k,i))?2:1,hav(a,b,i.lat,i.lng)]})}
                    out.lim={fb:items.map((i,k)=>({i,k})).filter(x=>vis(x.k)&&!nc(x.i)).map(x=>dists[x.k]).sort((x,y)=>x-y)};
                    for(const [k,D] of [['ws',window.WARMSPACES],['sh',window.SHELTERS]]){if(D)out.lim[k]=D.items.filter(i=>!(i.ended||V3.shutToday(k,i))).map(i=>hav(a,b,i.lat,i.lng)).sort((x,y)=>x-y)}
                    return out}""", [lat, lng])
                  lim = r.pop("lim")
                  self.assertTrue({"fb", sel} <= set(r), r.keys())
                  for k, rows in r.items():
                      if k not in ('fb', sel): continue
                      self.assertTrue(rows, (k, lat))
                      self.assertTrue(all(g < 2 for g, _ in rows), (k, lat, rows))
                      ds = [d for _, d in rows]; self.assertEqual(ds, sorted(ds), (k, lat, rows))
                      self.assertEqual([round(d, 6) for d in ds], [round(d, 6) for d in lim[k][:len(ds)]], (k, lat))  # exactly the nearest places not closed today
            # Open today OFF: every place, strictly nearest first (every layer)
            pg.click("#v3open"); pg.wait_for_timeout(300)
            for sel in ("ws", "sh"):
              pg.click(f".v3b[data-l={sel}]"); pg.wait_for_timeout(1000)
              for lat, lng in ((51.5074, -0.1278), (50.8095, -0.5405)):
                  r = pg.evaluate("""([a,b])=>{nearest(a,b,'test');const out={fb:[...document.querySelectorAll('#list .card')].map(c=>dists[+c.dataset.k])};
                    for(const [k,D] of [['ws',window.WARMSPACES],['sh',window.SHELTERS]]){if(!D)continue;
                      out[k]=[...document.querySelectorAll('#xlist .card.x'+k+' h3')].map(h=>{const i=D.items.find(x=>x.name===h.textContent);return hav(a,b,i.lat,i.lng)});
                      out['n'+k]=D.items.filter(i=>!i.ended).map(i=>hav(a,b,i.lat,i.lng)).sort((x,y)=>x-y).slice(0,3)}
                    return out}""", [lat, lng])
                  for k in ('fb', sel):
                      self.assertTrue(r[k], (k, lat)); self.assertEqual(r[k], sorted(r[k]), (k, lat))
                  self.assertEqual([round(x, 6) for x in r[sel]], [round(x, 6) for x in r['n' + sel]], (sel, lat))  # exactly the nearest, closed-today included
            c.close(); b.close()
