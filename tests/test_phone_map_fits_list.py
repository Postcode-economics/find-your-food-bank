"""owner 25 Oct 20:45: on phones the map must show the pins of the results LISTED for the chosen type (warm spaces/shelters can be
miles further than the nearest food banks). Nothing is ever filtered: the list is unchanged, the map just zooms out enough."""
import functools, http.server, os, threading, unittest
R = os.path.join(os.path.dirname(__file__), '..'); CH = '/usr/bin/google-chrome'
try:
    import playwright; HAVE = os.path.exists(CH)
except Exception: HAVE = False
CHECK = """k=>{const ln=lastNear,D=window[k==='sh'?'SHELTERS':'WARMSPACES'];if(!ln||!D)return {err:'not ready'};const R=6371,rad=x=>x*Math.PI/180;
 const hv=(a,b,c,d)=>2*R*Math.asin(Math.sqrt(Math.sin(rad(c-a)/2)**2+Math.cos(rad(a))*Math.cos(rad(c))*Math.sin(rad(d-b)/2)**2));
 const near=(D.items||D).filter(i=>!i.ended).map(i=>({i,d:hv(ln[0],ln[1],i.lat,i.lng)})).sort((a,b)=>a.d-b.d).slice(0,3);
 const B=map.getBounds();const cards=document.querySelectorAll('#xlist .card').length;
 return {cards,z:map.getZoom(),out:near.filter(x=>!B.contains([x.i.lat,x.i.lng])).map(x=>x.i.name+' '+x.d.toFixed(1)+'km')}}"""
class T(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'needs chrome + playwright')
    def test_phone_map_shows_listed_pins(self):
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=s.serve_forever, daemon=True).start(); bad = []
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH)
                for k in ('sh', 'ws'):
                    for q in ('SM1%201AA', 'IP1%202DA'):
                        c = b.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, service_workers='block')
                        c.add_init_script("try{localStorage.setItem('v3layer','%s')}catch(e){}" % k); pg = c.new_page()
                        pg.goto('http://127.0.0.1:%d/?nocount&q=%s' % (s.server_address[1], q)); pg.wait_for_timeout(9000)
                        r = pg.evaluate(CHECK, k)
                        if r.get('err') or r['out'] or r['cards'] < 1: bad.append((k, q, r))
                        c.close()
                b.close()
        finally: s.shutdown()
        self.assertEqual(bad, [])
if __name__ == '__main__': unittest.main()
