"""Two-finger map note (Dean 25 Oct 11:31): shown at most 2 times per visitor (localStorage hmTwoFinger), then never again."""
import functools, http.server, os, threading, unittest
R = os.path.join(os.path.dirname(__file__), '..'); CH = '/usr/bin/google-chrome'
DRAG = """()=>{const m=document.querySelector('#map');const r=m.getBoundingClientRect();const x=r.left+r.width/2,y=r.top+r.height/2;
 const t=(cx,cy)=>new Touch({identifier:1,target:m,clientX:cx,clientY:cy});
 m.dispatchEvent(new TouchEvent('touchstart',{touches:[t(x,y)],targetTouches:[t(x,y)],bubbles:true,cancelable:true}));
 m.dispatchEvent(new TouchEvent('touchmove',{touches:[t(x+60,y+60)],targetTouches:[t(x+60,y+60)],bubbles:true,cancelable:true}));
 m.dispatchEvent(new TouchEvent('touchend',{touches:[],targetTouches:[],bubbles:true,cancelable:true}));
 return document.querySelector('.mgest').classList.contains('on')}"""
class T(unittest.TestCase):
    def test_static(self):
        h = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        self.assertIn("localStorage.getItem('hmTwoFinger')", h); self.assertIn('if(n>=2)return', h)
    @unittest.skipUnless(os.path.exists(CH), 'needs chrome')
    def test_max_two(self):
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=s.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH)
                c = b.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True, service_workers='block'); pg = c.new_page()
                pg.goto('http://127.0.0.1:%d/?nocount' % s.server_address[1], wait_until='networkidle'); pg.wait_for_timeout(800)
                pg.evaluate("document.querySelector('#map').scrollIntoView()")
                shown = []
                for _ in range(4):
                    shown.append(pg.evaluate(DRAG)); pg.wait_for_timeout(1800)
                self.assertEqual(shown, [True, True, False, False])
                pg.reload(wait_until='networkidle'); pg.wait_for_timeout(800); pg.evaluate("document.querySelector('#map').scrollIntoView()")
                self.assertFalse(pg.evaluate(DRAG)); b.close()
        finally: s.shutdown()
