"""sw.js: no leftover Stadia host; OpenFreeMap backup tiles are cached (27 Oct 2026)."""
import json, shutil, subprocess, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SW = (ROOT / 'sw.js').read_text(encoding='utf-8')

HARNESS = r"""
const fs=require('fs');const src=fs.readFileSync(process.argv[1],'utf8');
const store=new Map();let net=0,offline=false;const H={};
const cache={match:async r=>store.get(r.url||r),put:async(r,v)=>{store.set(r.url||r,v)},keys:async()=>[...store.keys()].map(url=>({url})),delete:async r=>store.delete(r.url||r),addAll:async()=>{}};
global.caches={open:async()=>cache,keys:async()=>[],match:async()=>undefined,delete:async()=>true};
global.self={addEventListener:(t,f)=>{H[t]=f},clients:{matchAll:async()=>[],claim:async()=>{}},skipWaiting:()=>{}};
global.Response={error:()=>({error:true})};
global.fetch=async r=>{net++;if(offline)throw new Error('off');return {ok:true,body:'net:'+(r.url||r),clone(){return this}}};
new Function(src)();
const go=async url=>{let p;H.fetch({request:{url,method:'GET',mode:'cors'},respondWith:x=>{p=x}});return p?await p:'passthrough'};
(async()=>{const out={};
 const tile='https://tiles.openfreemap.org/planet/20261025_080012_pt/6/31/20.pbf';
 await go(tile);const n1=net;const r2=await go(tile);out.tile_cache_first=(net===n1&&r2.body==='net:'+tile);
 const font='https://tiles.openfreemap.org/fonts/Noto%20Sans%20Regular/0-255.pbf';await go(font);out.font_cached=store.has(font);
 const style='https://tiles.openfreemap.org/styles/positron';await go(style);const n2=net;await go(style);out.style_network_first=(net===n2+1);
 offline=true;const r3=await go(style);out.style_offline=(r3.body==='net:'+style);
 const r4=await go(tile);out.tile_offline=(r4.body==='net:'+tile);
 out.stadia_passthrough=(await go('https://tiles.stadiamaps.com/tiles/osm_bright/1/0/0.png'))==='passthrough';
 console.log(JSON.stringify(out))})();
"""


class SwOfm(unittest.TestCase):
    def test_no_stadia_host_left(self):
        self.assertNotIn('stadia', SW.lower())

    def test_ofm_host_handled(self):
        self.assertIn(r'tiles\.openfreemap\.org', SW)

    def test_ofm_behaviour_in_node(self):
        node = shutil.which('node')
        if not node: raise unittest.SkipTest('node not installed')
        out = subprocess.run([node, '-e', HARNESS, str(ROOT / 'sw.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout.strip().splitlines()[-1])
        for k, v in got.items():
            self.assertTrue(v, k)
        self.assertEqual(len(got), 6)


if __name__ == '__main__':
    unittest.main()
