"""Rule 85 (Dean): every donations-only food bank place (kind warehouse/dropoff) uses one uniform
layout. Map pin = whIcon (white rounded square #F2F4F8, dark #0A1628 outline, dark down arrow),
also when selected; card = 'Donations only' ncb banner + box icon + 'Get food at:' list.
New listings with those kinds get it automatically because nc() keys only on kind."""
import json, os, re, subprocess, unittest
ROOT = os.path.join(os.path.dirname(__file__), '..')
HTML = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
NODE = r'''
const fs=require('fs'),vm=require('vm');const ctx={};ctx.window=ctx;vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const items=ctx.FB_DATA.items;const nc=i=>i.kind==='warehouse'||i.kind==='dropoff';
const W={n:'wh'},Y={n:'bag'},S={n:'sel'};const icFor=k=>nc(items[k])?W:Y;
const out={wh:0,dropoff:0,warehouse:0,bad:[],nopin:[]};
items.forEach((i,k)=>{if(!nc(i))return;out[i.kind]++;if(i.lat==null||i.lng==null)out.nopin.push(i.id);
 const sel=nc(i)?W:S;if(icFor(k)!==W||sel!==W)out.bad.push(i.id);else out.wh++;});
for(const kind of ['warehouse','dropoff']){items.push({id:'new-'+kind,kind});if(icFor(items.length-1)!==W)out.bad.push('new-'+kind);}
console.log(JSON.stringify(out));'''

class DonationPins(unittest.TestCase):
    def test_source_wiring(self):
        self.assertIn("const nc=i=>i.kind==='warehouse'||i.kind==='dropoff';", HTML)
        m = re.search(r"const whIcon=L\.divIcon\(\{className:'pin wh',html:'([^']+)'", HTML)
        self.assertTrue(m, 'whIcon missing')
        svg = m.group(1)
        for s in ('rx="3"', 'fill="#F2F4F8"', 'stroke="#0A1628"', 'M15 2v14m-6-5 6 6 6-6'):
            self.assertIn(s, svg)
        self.assertIn('const icFor=k=>nc(items[k])?whIcon:icon;', HTML)
        self.assertIn('m.setIcon(nc(i)?whIcon:selIcon)', HTML)
        self.assertIn('markers[selected].setIcon(icFor(selected))', HTML)
        self.assertIn('if(nc(i))return `<div class="ncb" role="note">${ncl(i)}</div>', HTML)
        self.assertIn('<div class="lh">Get food at:</div>', HTML)
        self.assertIn("${IC('box')}<span>${esc(i.label_en)}</span>", HTML)

    def test_every_record(self):
        r = subprocess.run(['node', '-e', NODE, os.path.join(ROOT, 'data.js')], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        o = json.loads(r.stdout)
        self.assertEqual(o['bad'], [])
        self.assertEqual(o['nopin'], [])
        self.assertGreater(o['wh'], 0)
        self.assertEqual(o['wh'], o['warehouse'] + o['dropoff'])
        print('donation pins', o['warehouse'], o['dropoff'])

if __name__ == '__main__':
    unittest.main()
