"""Data parity (Dean 24 Oct): every listing rendered old vs new look must carry identical data."""
import http.server, functools, threading, os, unittest, json
ROOT = os.path.join(os.path.dirname(__file__), "..")
EXTRACT = r"""(html)=>{const t=document.createElement('div');t.className='card';t.innerHTML=html;if(window.NL&&arguments.length)0;return t}"""
JS = r"""
(async()=>{
 // data = every link target + every piece of text outside the buttons (button text is only a label for its link) + labels/tags + status + hours rows
 const sig=el=>{const c=el.cloneNode(true);const links=[...c.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')).sort();
   const tags=[...c.querySelectorAll('.tag:not(.nltag),.xacc,.xunv,.ncb')].map(e=>e.textContent.trim());
   const btxt=[...c.querySelectorAll('a.btn.xfb')].map(e=>e.textContent.replace(/\s+/g,''));
   c.querySelectorAll('a.btn,button.btn,.nltag').forEach(e=>e.remove());
   const words=c.textContent.replace(/\s+/g,'');const chars=[...words].sort().join('');
   const st=(el.querySelector('.v3st')||{}).textContent||'';const rows=[...el.querySelectorAll('table tr')].map(r=>r.textContent.replace(/\s+/g,''));
   return JSON.stringify({links,tags,btxt,chars,st,rows,rp:[...el.querySelectorAll('.rpb')].map(b=>b.dataset.rid)})};
 const wrap=h=>{const t=document.createElement('div');t.className='card';t.innerHTML=h;return t};
 const out={fb:[0,[]],ws:[0,[]],sh:[0,[]]};
 for(let k=0;k<items.length;k++){const i=items[k];const a=wrap(window.__oc(i,1.2)),b=wrap(window.card(i,1.2));NL.apply(b);
   out.fb[0]++;if(sig(a)!==sig(b))out.fb[1].push(i.name)}
 for(const [k,src] of [['ws','WARMSPACES'],['sh','SHELTERS']]){const its=(window[src]||{}).items||[];
   for(const i of its){const h=window.__detail(k,i,1.2);const a=wrap(h),b=wrap(h);b.classList.add('x'+k);NL.apply(b);out[k][0]++;if(sig(a)!==sig(b))out[k][1].push(i.name)}}
 return out})()"""

class Parity(unittest.TestCase):
    def test_every_listing_identical(self):
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT); h.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path="/usr/bin/google-chrome"); pg = b.new_page(viewport={"width": 390, "height": 844})
                def rt(route):
                    r = route.fetch(); t = r.text(); i = t.rindex('})();'); route.fulfill(response=r, body=t[:i] + 'window.__detail=detail;' + t[i:])
                pg.route('**/layers.js*', rt)
                def rv3(route):  # keep a handle on the card renderer from before the new look wraps it
                    r = route.fetch(); route.fulfill(response=r, body='window.__oc=window.card;' + r.text())
                pg.route('**/newlook.js*', rv3)
                port = srv.server_address[1]
                pg.goto(f"http://127.0.0.1:{port}/?fresh=1", wait_until="networkidle"); pg.wait_for_timeout(1500)
                for f in ("shelters.js", "warmspaces.js"): pg.add_script_tag(url=f"http://127.0.0.1:{port}/{f}")
                pg.wait_for_timeout(800)
                r = pg.evaluate(JS); b.close()
        finally: srv.shutdown()
        print(json.dumps({k: [v[0], len(v[1])] for k, v in r.items()}))
        exp = {"fb": 3000, "ws": 411, "sh": 99}
        for k, (n, bad) in r.items():
            self.assertGreaterEqual(n, exp[k] * 0.9, k); self.assertEqual(bad, [], k)
