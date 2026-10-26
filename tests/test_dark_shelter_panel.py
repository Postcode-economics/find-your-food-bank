"""owner 25 Oct 20:37 (v88b test): in dark mode the shelter 'Sleeping rough / StreetLink' panel was a near-white box and the
Call 999 was navy. Dark panel with readable text in dark mode; Call 999 bold white text + icon on #FF3B30 in BOTH modes."""
import functools, http.server, os, threading, unittest
R = os.path.join(os.path.dirname(__file__), '..'); CH = '/usr/bin/google-chrome'
try:
    import playwright; HAVE = os.path.exists(CH)
except Exception: HAVE = False
def lum(rgb):
    v = [int(x) / 255 for x in rgb.replace('rgba(', '').replace('rgb(', '').rstrip(')').split(',')[:3]]
    v = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in v]; return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True); return (la + 0.05) / (lb + 0.05)
class T(unittest.TestCase):
    @unittest.skipUnless(HAVE, 'needs chrome + playwright')
    def test_dark_panel(self):
        from playwright.sync_api import sync_playwright
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=R); h.log_message = lambda *a: None
        s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), h); threading.Thread(target=s.serve_forever, daemon=True).start(); bad = []
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=CH)
                for w, mode in ((390, 'dark'), (1366, 'dark'), (390, 'light'), (1366, 'light')):
                    c = b.new_context(viewport={'width': w, 'height': 844}, color_scheme=mode, service_workers='block')
                    c.add_init_script("try{localStorage.setItem('v3layer','sh');localStorage.setItem('light','%s')}" % ('1' if mode == 'light' else '0') + "catch(e){}"); pg = c.new_page()
                    pg.goto('http://127.0.0.1:%d/?nocount&q=SM1%%201AA' % s.server_address[1]); pg.wait_for_timeout(8000)
                    r = pg.evaluate("""(()=>{const vis=[...document.querySelectorAll('.v3sos')].filter(e=>e.offsetParent);const lh=[...document.querySelectorAll('#xlist>.lh')].find(e=>e.offsetParent);
                      const s9=vis.map(e=>e.querySelector('a.sosl.s999')).filter(Boolean);const page=getComputedStyle(document.body).backgroundColor;
                      return {n:vis.length,p:vis.map(e=>[getComputedStyle(e).backgroundColor,getComputedStyle(e).color]),s9:s9.map(a=>{const i=a.querySelector('svg,.ico');return [getComputedStyle(a).backgroundColor,getComputedStyle(a).color,getComputedStyle(a).fontWeight,i?getComputedStyle(i).color:'rgb(255, 255, 255)']}),
                        lh:lh?getComputedStyle(lh).color:null,page}})()""")
                    if not r['n']: bad.append((w, 'no StreetLink panel')); continue
                    for bg, fg in (r['p'] if mode == 'dark' else []):
                        if lum(bg) > 0.2: bad.append((w, 'panel is a light box in dark mode', bg))
                        if ratio(bg, fg) < 7: bad.append((w, 'panel text contrast', bg, fg))
                    if not r['s9']: bad.append((w, mode, 'no Call 999 button'))
                    for bg, fg, fw, ic in r['s9']:
                        if bg != 'rgb(255, 59, 48)' or fg != 'rgb(255, 255, 255)' or int(fw) < 700 or ic != 'rgb(255, 255, 255)': bad.append((w, mode, 'Call 999 not bold white (text+icon) on #FF3B30', bg, fg, fw, ic))
                    c.close()
                b.close()
        finally: s.shutdown()
        self.assertEqual(bad, [])
if __name__ == '__main__': unittest.main()
