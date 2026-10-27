"""Batch 4 / Operation Warp Speed (27 Oct 2026): sw.js behaviour, run in node with fake caches/fetch.
1. An <img> (no-cors) OpenStreetMap tile is fetched in cors mode and stored, so a repeat visit is served from cache.
2. data.js with a ?v=h<hash> stamp is cache-first; a new stamp fetches fresh and drops the old stamped copy;
   offline, the last copy still answers. Unstamped data.js stays network-first."""
import json, os, re, shutil, subprocess, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
HARNESS = r"""
const fs=require('fs');const src=fs.readFileSync(process.argv[1],'utf8');
const store=new Map();let net=[],offline=false;const H={};const key=r=>r.url||r;
const cache={match:async r=>store.get(key(r)),put:async(r,v)=>{store.set(key(r),v)},keys:async()=>[...store.keys()].map(url=>({url})),delete:async r=>store.delete(key(r)),addAll:async()=>{}};
global.caches={open:async()=>cache,keys:async()=>[],match:async r=>store.get(key(r)),delete:async()=>true};
global.self={addEventListener:(t,f)=>{H[t]=f},clients:{matchAll:async()=>[],claim:async()=>{}},skipWaiting:()=>{}};
global.location={origin:'https://helpmap.uk',href:'https://helpmap.uk/'};
global.Request=function(u,o){this.url=u;Object.assign(this,o||{})};
global.Response={error:()=>({error:true})};
global.fetch=async r=>{net.push([r.url||r,r.mode]);if(offline)throw new Error('off');const mode=r.mode||'cors',op=mode==='no-cors'&&!String(r.url||r).startsWith(location.origin);return {ok:!op,type:op?'opaque':'cors',body:'net:'+(r.url||r)+'#'+net.length,clone(){return this}}};
new Function(src)();
const go=async(url,mode)=>{let p;H.fetch({request:{url,method:'GET',mode:mode||'no-cors',destination:String(url).includes('tile.')?'image':'script'},respondWith:x=>{p=x},waitUntil:()=>{}});return p?await p:'passthrough'};
const tick=()=>new Promise(r=>setTimeout(r,20));
(async()=>{const o={};
 const t='https://tile.openstreetmap.org/6/31/20.png';
 await go(t,'no-cors');await tick();o.img_fetched_cors=net[0][1]==='cors';o.img_tile_stored=store.has(t);
 const n=net.length;const r=await go(t,'no-cors');o.repeat_from_cache=net.length===n&&!r.error;
 const a='https://helpmap.uk/data.js?v=haaaaaaaaaaaa',b='https://helpmap.uk/data.js?v=hbbbbbbbbbbbb';
 const r1=await go(a,'no-cors');const n2=net.length;const r2=await go(a,'no-cors');o.stamped_cache_first=net.length===n2&&r2.body===r1.body;
 const r3=await go(b,'no-cors');o.new_stamp_fetched=r3.body!==r1.body&&net.length===n2+1;o.old_stamp_dropped=!store.has(a);
 const n3=net.length;await go('https://helpmap.uk/data.js','no-cors');o.unstamped_network_first=net.length===n3+1;
 offline=true;const r4=await go('https://helpmap.uk/data.js?v=hcccccccccccc','no-cors');o.offline_last_copy=!!r4.body;
 console.log(JSON.stringify(o))})();
"""
class WarpSW(unittest.TestCase):
    def test_sw_behaviour(self):
        node = shutil.which('node')
        if not node: raise unittest.SkipTest('node not installed')
        out = subprocess.run([node, '-e', HARNESS, str(ROOT / 'sw.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(len(got), 8, got)
        for k, v in got.items(): self.assertTrue(v, k)
    def test_index_stamps_match_file_hashes(self):
        import seo_meta as SM
        h = (ROOT / 'index.html').read_text(encoding='utf-8')
        for f in ('data', 'stamp', 'access'):
            self.assertIn('<script src="%s.js?v=%s"></script>' % (f, SM.content_stamp(str(ROOT), f + '.js')), h)
if __name__ == '__main__': unittest.main()
