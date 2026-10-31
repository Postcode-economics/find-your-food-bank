"""Display-only opening times (Dean, 31 Oct 2026).

Free-text lines become short day names plus 24-hour HH:MM–HH:MM. A line that is not
safe to read stays as written. A card that already shows times does not say
'Times unknown'. Saturday with a table that skips today says when it is next open.
"""
import json, os, subprocess, unittest
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
NODE = r'''
const fs=require('fs'), vm=require('vm');
const ctx={window:{}, document:{documentElement:{lang:'en'}}, history:{scrollRestoration:''}, navigator:{}, location:{search:''}, localStorage:{getItem(){return null}, setItem(){}}};
ctx.window=ctx; vm.createContext(ctx);
try{ vm.runInContext(fs.readFileSync(process.argv[1],'utf8'), ctx); }catch(e){}
const F=ctx.timesFmt;
const cases=JSON.parse(process.argv[2]);
const out=cases.map(c=>{
  const got=F.tryParse(c[0]);
  return got?got.join(' | '):null;
});
const lines=F.lines(JSON.parse(process.argv[3]));
process.stdout.write(JSON.stringify({out, lines}));
'''

def fmt(cases, lines=None):
    cmd=['node','-e',NODE,os.path.join(ROOT,'v3.js'),json.dumps(cases),json.dumps(lines or [])]
    r=subprocess.run(cmd,capture_output=True,text=True,check=True)
    return json.loads(r.stdout)

class Formatter(unittest.TestCase):
    def test_named_examples(self):
        cases=[
            ['Monday - 12:30 - 2.30pm','Mon 12:30–14:30'],
            ['Wednesday - 10am - 12','Wed 10:00–12:00'],
            ['Friday - 12:30 - 2.30','Fri 12:30–14:30'],
            ['Monday 12.30pm - 3pm','Mon 12:30–15:00'],
            ['Friday 12.30pm - 3pm','Fri 12:30–15:00'],
            ['Monday – 10am-3pm','Mon 10:00–15:00'],
            ['Mondays to Thursdays from 10.00am-3.00pm','Mon–Thu 10:00–15:00'],
            ['Sundays from 08.30am-1.00pm','Sun 08:30–13:00'],
            ['Monday Drop in 12pm-2pm','Mon 12:00–14:00'],
            ['Tuesday 10am-2pm','Tue 10:00–14:00'],
            ['Wednesday 10am-2pm','Wed 10:00–14:00'],
            ['Thursday 10am-2pm','Thu 10:00–14:00'],
            ['Friday 9am-11am','Fri 09:00–11:00'],
            ['Monday to Friday 09:00 – 16:00pm','Mon–Fri 09:00–16:00'],
            ['Weds 09;00 – 12:00pm','Wed 09:00–12:00'],
            ['Mon & Weds 14:30pm – 15:30pm','Mon, Wed 14:30–15:30'],
            ['Mon, Tues, Thurs, Fri 09:00 – 16:00pm','Mon, Tue, Thu, Fri 09:00–16:00'],
            ['Tues and Thurs 10:00 – 16:00pm','Tue, Thu 10:00–16:00'],
            ['Thursday 09:30 – 10:30am','Thu 09:30–10:30'],
            ['Wednesday 10:00am – 12:30pm','Wed 10:00–12:30'],
            ['Friday: 10am - midday','Fri 10:00–12:00'],
            ['Wednesdays 12 noon to 3.00 pm','Wed 12:00–15:00'],
            ['Monday to Friday, 10:00 - noon','Mon–Fri 10:00–12:00'],
            ['Tuesday & Thursday 9am to 12pm and 1pm to 4pm','Tue, Thu 09:00–12:00, 13:00–16:00'],
            ['Wed 10am-12pm monthly','Wed 10:00–12:00 Monthly'],
            ['Mondays through Thursday 9.30am to 5.00pm','Mon–Thu 09:30–17:00'],
        ]
        got=fmt([[c[0]] for c in cases])['out']
        for (src,exp),g in zip(cases,got):
            self.assertEqual(g,exp,src)

    def test_calne_keeps_both_monday_times_and_drops_the_duplicate(self):
        lines=['Monday - 12:30 - 2.30pm','Wednesday - 10am - 12','Friday - 12:30 - 2.30',
               'Monday 12.30pm - 3pm','Wednesday 10am - 12','Friday 12.30pm - 3pm']
        self.assertEqual(fmt([],lines)['lines'],[
            'Mon 12:30–14:30','Wed 10:00–12:00','Fri 12:30–14:30','Mon 12:30–15:00','Fri 12:30–15:00'])

    def test_ambiguous_and_caveated_lines_stay_as_written(self):
        keep=[
            'Monday to Friday (Appointments only) 09:00 – 15:30pm',
            'Thursday – – – Friday – 10 AM – 4 PM',
            'Wednesday’s and 9 am to 3 pm',
            '2.30 - 4.30',
            'Tuesday and Friday morning (unless otherwise advertised) from 10:00 to 12:00',
            'Delivery only (no collection here). Phoneline open Tuesday to Friday, 10am to 12:30pm, not collection times',
            '19:30-07:30',
            'Open 24 hours, 365 days a year. Call 01642 800311 for a bed (agency referrals Mon-Fri 9am-5pm)',
            'Fridays only',
            'Friday morning from 10.00am-12.00am',
        ]
        got=fmt([[c] for c in keep])['out']
        for src,g in zip(keep,got):
            self.assertIsNone(g,src)
            self.assertEqual(fmt([], [src])['lines'], [src])

import functools, http.server, threading
try:
    import playwright
    HAVE=os.path.exists('/usr/bin/google-chrome')
except Exception:
    HAVE=False

@unittest.skipUnless(HAVE, 'needs chrome + playwright')
class Badges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        h=functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
        h.log_message=lambda *a: None
        cls.srv=http.server.ThreadingHTTPServer(('127.0.0.1',0), h)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base='http://127.0.0.1:%d/?nocount&fresh=1'%cls.srv.server_address[1]
    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_each_badge_case(self):
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from site_ready import open_map
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b=p.chromium.launch(executable_path='/usr/bin/google-chrome')
            c=b.new_context(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True, service_workers='block')
            pg=c.new_page(); open_map(pg, self.base); pg.wait_for_timeout(400)
            got=pg.evaluate(r'''()=>{
              function on(d){history.replaceState(null,'','/?testdate='+d); }
              function en(html){const e=document.createElement('div'); e.innerHTML=html; return e.querySelector('.v-en').textContent}
              function cy(html){const e=document.createElement('div'); e.innerHTML=html; return e.querySelector('.v-cy').textContent}
              const chel={opening_times:{status:'TIMES_FOUND', structured:{mon:[['10:00','15:00']],tue:[['10:00','15:00']],wed:[['10:00','15:00']],thu:[['10:00','15:00']],sun:[['08:30','13:00']]}}};
              const calne={opening_times:{status:'TIMES_TEXT_ONLY', raw:'x', lines:['Monday - 12:30 - 2.30pm','Wednesday - 10am - 12','Monday 12.30pm - 3pm']}};
              const closedMon={opening_times:{status:'TIMES_FOUND', structured:{tue:[['10:00','12:00']]}, closed:['mon']}};
              const fortnight={opening_times:{status:'TIMES_FOUND', structured:{wed:[['10:00','12:00']]}, notes:{wed:'Fortnightly'}}};
              const monthly={hours:{Thu:'10:30 - 12:00 Monthly'}};
              const none={};
              const textSh={hours:'Monday Drop in 12pm-2pm'};
              const ref={hours:'By referral, call to arrange'};
              const call={call_check:true, hours:{}};
              on('2026-10-31'); // Saturday
              const satChel=V3.badge('fb', chel), satCalne=V3.badge('fb', calne);
              on('2026-10-28'); // Wednesday noon via pageNow
              const wedChel=V3.badge('fb', chel);
              on('2026-10-26'); // Monday
              const monClosed=V3.badge('fb', closedMon);
              on('2026-10-31');
              return {
                satChel: en(satChel), satChelCy: cy(satChel),
                satCalne: en(satCalne), satCalneCy: cy(satCalne),
                wedChel: en(wedChel),
                monClosed: en(monClosed),
                fortn: en(V3.badge('fb', fortnight)), fortnCy: cy(V3.badge('fb', fortnight)),
                month: en(V3.badge('ws', monthly)), monthCy: cy(V3.badge('ws', monthly)),
                none: en(V3.badge('fb', none)),
                text: en(V3.badge('sh', textSh)), textCy: cy(V3.badge('sh', textSh)),
                ref: en(V3.badge('sh', ref)),
                call: en(V3.badge('ws', call)),
                lines: timesFmt.lines(calne.opening_times.lines)
              };
            }''')
            c.close(); b.close()
        self.assertEqual(got['satChel'], 'Next open: Sun 08:30–13:00 – call before you go')
        self.assertNotIn('Times unknown', got['satChel'])
        self.assertNotIn('Closed', got['satChel'])
        self.assertEqual(got['satChelCy'], 'Ar agor nesaf: Sul 08:30–13:00 – ffoniwch cyn mynd')
        self.assertEqual(got['satCalne'], 'Check times below – call before you go')
        self.assertEqual(got['satCalneCy'], 'Gwiriwch yr amseroedd isod – ffoniwch cyn mynd')
        self.assertIn('OPEN NOW until 15:00', got['wedChel'])
        self.assertIn('Closed', got['monClosed'])
        self.assertIn('Tue 10:00–12:00', got['monClosed'])
        self.assertNotIn('Times unknown', got['monClosed'])
        self.assertEqual(got['fortn'], 'Check dates – call before you go')
        self.assertEqual(got['fortnCy'], 'Gwiriwch y dyddiadau – ffoniwch cyn mynd')
        self.assertEqual(got['month'], 'Check dates – call before you go')
        self.assertEqual(got['monthCy'], 'Gwiriwch y dyddiadau – ffoniwch cyn mynd')
        self.assertEqual(got['none'], 'Times unknown – call before you go')
        self.assertEqual(got['text'], 'Check times below – call before you go')
        self.assertEqual(got['textCy'], 'Gwiriwch yr amseroedd isod – ffoniwch cyn mynd')
        self.assertIn('By referral', got['ref'])
        self.assertEqual(got['call'], 'Times unknown – call before you go')
        self.assertEqual(got['lines'], ['Mon 12:30–14:30','Wed 10:00–12:00','Mon 12:30–15:00'])

    def test_saturday_cards_calne_and_cheltenham(self):
        from playwright.sync_api import sync_playwright
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from site_ready import open_map
        base=self.base+'&testdate=2026-10-31'
        with sync_playwright() as p:
            b=p.chromium.launch(executable_path='/usr/bin/google-chrome')
            c=b.new_context(viewport={'width':390,'height':844}, is_mobile=True, has_touch=True, device_scale_factor=2, service_workers='block')
            pg=c.new_page(); open_map(pg, base); pg.wait_for_timeout(500)
            places=[
                ('Calne Foodbank', 51.4403959, -2.0050154,
                 ['Mon 12:30–14:30','Wed 10:00–12:00','Fri 12:30–14:30','Mon 12:30–15:00','Fri 12:30–15:00'],
                 'Check times below – call before you go'),
                ('Cheltenham Open Door', 51.9025996, -2.0968695,
                 ['Sun\t08:30–13:00'],
                 'Next open: Sun 08:30–13:00 – call before you go'),
            ]
            for name, lat, lng, lines, badge in places:
                pg.evaluate('([a,b,n])=>nearest(a,b,n)', [lat, lng, name])
                pg.wait_for_timeout(400)
                card=pg.locator('#list .card').first
                text=card.inner_text()
                self.assertIn(name.split()[0], text)
                self.assertNotIn('Times unknown', text)
                self.assertIn(badge, text)
                for line in lines:
                    self.assertIn(line.split('\t')[-1], text)
                if 'Cheltenham' in name:
                    self.assertNotRegex(text, r'(?m)^Closed$')
                    self.assertIn('08:30–13:00', text)
            c.close(); b.close()
