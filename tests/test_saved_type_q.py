"""25 Oct 2026 (v88b live test t4): opening /?q=LN5 7PR with Warm space or Shelter saved as the type showed the type selected but the
status line and list were food banks. The saved type and the ?q= search must agree on load."""
import functools, http.server, os, sys, threading, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import check_browser as B
R = os.path.join(os.path.dirname(__file__), '..'); CH = '/usr/bin/google-chrome'
try:
    import playwright; HAVE = os.path.exists(CH)
except Exception: HAVE = False
class T(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'needs chrome + playwright')
    def test_saved_type_wins_on_q_link(self):
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=s.serve_forever, daemon=True).start()
        bad = []
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH)
                for k, want in (('ws', 'Warm spaces near'), ('sh', 'Shelters near'), ('fb', 'Food banks near')):
                    for w, slow in ((390, False), (1366, False), (390, True), (1366, True)):
                        c = b.new_context(viewport={'width': w, 'height': 800}, service_workers='block')
                        B.stub_map_tiles(c)  # rule 23: a desktop map must not fetch real tiles (that stalls this restore)
                        c.add_init_script("try{if(!sessionStorage.getItem('t4')){sessionStorage.setItem('t4','1');localStorage.setItem('v3layer','%s');localStorage.setItem('lastSearch',JSON.stringify({lat:51.5,lng:-0.12,label:'London'}))}}catch(e){}" % k); pg = c.new_page()
                        if slow: c.route('**/v3.js*', lambda r: (__import__('time').sleep(2.5), r.continue_()))   # v3.js restores the type AFTER the ?q search lands (fast cached lookup)
                        pg.goto('http://127.0.0.1:%d/?nocount&q=LN5%%207PR' % s.server_address[1], wait_until='load')
                        txt = ''
                        for _ in range(40):
                            txt = pg.evaluate("(document.querySelector('#v3pill .v3pl .v-en')||document.querySelector('#v3pill .v3pl')||{}).textContent||''")
                            if txt.startswith(want): break
                            pg.wait_for_timeout(500)
                        pg.wait_for_timeout(6000)   # and it must STAY that way once every load-time search has landed
                        txt = pg.evaluate("(document.querySelector('#v3pill .v3pl .v-en')||document.querySelector('#v3pill .v3pl')||{}).textContent||''")
                        lst = pg.evaluate("(()=>{const l=document.getElementById(%s);return l&&l.offsetParent?l.querySelectorAll('.card').length:0})()" % ("'list'" if k == 'fb' else "'xlist'"))
                        if lst < 1: bad.append((k, w, 'no %s cards shown' % k))
                        sel = pg.evaluate("(document.querySelector('#v3big .v3b[aria-checked=true]')||{}).dataset.l")
                        if not txt.startswith(want) or sel != k: bad.append((k, w, slow, sel, txt))
                        c.close()
                b.close()
        finally: s.shutdown()
        self.assertEqual(bad, [])
if __name__ == '__main__': unittest.main()
