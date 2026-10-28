"""Batch 4 / Operation Warp Speed (27 Oct 2026): sw.js behaviour, run in node with fake caches/fetch.
1. An <img> (no-cors) OpenStreetMap tile is fetched in cors mode and stored, so a repeat visit is served from cache.
   The tiles.js probe and the <img> for the same tile, the second arriving before the first copy is stored, make one
   network request between them.
2. data.js with a ?v=h<hash> stamp is kept: a repeat visit sends one conditional request and, on a 304, is served the
   saved copy (no download); a file changed under the same stamp is fetched and saved (freshness rule, 26 Oct 2026);
   a new stamp fetches fresh and drops the old stamped copy; offline, the last copy still answers.
   Unstamped data.js stays network-first."""
import json, os, re, shutil, subprocess, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
HARNESS = r"""
const fs=require('fs');const src=fs.readFileSync(process.argv[1],'utf8');
const store=new Map();let net=[],offline=false,slowPut=0;const H={};const key=r=>r.url||r;
const cache={match:async r=>store.get(key(r)),put:async(r,v)=>{if(slowPut)await new Promise(x=>setTimeout(x,slowPut));store.set(key(r),v)},keys:async()=>[...store.keys()].map(url=>({url})),delete:async r=>store.delete(key(r)),addAll:async()=>{}};
global.caches={open:async()=>cache,keys:async()=>[],match:async r=>store.get(key(r)),delete:async()=>true};
global.self={addEventListener:(t,f)=>{H[t]=f},clients:{matchAll:async()=>[],claim:async()=>{}},skipWaiting:()=>{}};
global.location={origin:'https://helpmap.uk',href:'https://helpmap.uk/'};
global.Request=function(u,o){if(u&&u.url){Object.assign(this,u)}else{this.url=u}Object.assign(this,o||{})};const ver={};
global.Response={error:()=>({error:true})};
global.fetch=async(r,q)=>{const url=r.url||r,hd=(q&&q.headers)||r.headers||{};net.push([url,r.mode,!!hd['If-None-Match']]);if(offline)throw new Error('off');
 const et='"'+(ver[String(url).split('?')[0]]||0)+'"',hs={get:n=>n==='etag'?et:null};if(hd['If-None-Match']===et)return {status:304,ok:false,type:'basic',headers:{get:()=>null},clone(){return this}};
 const mode=r.mode||'cors',op=mode==='no-cors'&&!String(url).startsWith(location.origin);return {status:op?0:200,ok:!op,type:op?'opaque':'cors',headers:hs,body:'net:'+url+'#'+net.length,clone(){return this}}};
new Function(src)();
const start=(url,mode)=>{let p;H.fetch({request:{url,method:'GET',mode:mode||'no-cors',destination:String(url).includes('tile.')?'image':'script'},respondWith:x=>{p=x},waitUntil:()=>{}});return p||Promise.resolve('passthrough')};
const go=async(url,mode)=>await start(url,mode);
const tick=()=>new Promise(r=>setTimeout(r,20));
(async()=>{const o={};
 const t='https://tile.openstreetmap.org/6/31/20.png';
 await go(t,'no-cors');await tick();o.img_fetched_cors=net[0][1]==='cors';o.img_tile_stored=store.has(t);
 const n=net.length;const r=await go(t,'no-cors');o.repeat_from_cache=net.length===n&&!r.error;
 const a='https://helpmap.uk/data.js?v=haaaaaaaaaaaa',b='https://helpmap.uk/data.js?v=hbbbbbbbbbbbb';
 const r1=await go(a,'no-cors');const n2=net.length;const r2=await go(a,'no-cors');o.stamped_revalidated_304=net.length===n2+1&&net[n2][2]===true&&r2.body===r1.body;
 ver['https://helpmap.uk/data.js']=1;const r5=await go(a,'no-cors');o.same_stamp_change_fetched=r5.body!==r1.body&&store.get(a).body===r5.body;
 const nb=net.length;const r3=await go(b,'no-cors');o.new_stamp_fetched=r3.body!==r5.body&&net.length===nb+1;o.old_stamp_dropped=!store.has(a);
 const n3=net.length;await go('https://helpmap.uk/data.js','no-cors');o.unstamped_network_first=net.length===n3+1;
 slowPut=50;const t2='https://tile.openstreetmap.org/7/63/41.png',n4=net.length;
 const pr=start(t2,'cors');await new Promise(x=>setTimeout(x,5));const im=start(t2,'no-cors');const [q1,q2]=await Promise.all([pr,im]);
 o.one_request_per_tile=net.filter(x=>x[0]===t2).length===1&&net.length===n4+1&&!q1.error&&!q2.error&&store.has(t2);slowPut=0;
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
        self.assertEqual(len(got), 10, got)
        for k, v in got.items(): self.assertTrue(v, k)
    def test_index_stamps_match_file_hashes(self):
        import seo_meta as SM
        h = (ROOT / 'index.html').read_text(encoding='utf-8')
        for f in ('data', 'stamp', 'access'):
            tags = re.findall(r'<script\b[^>]*\bsrc="%s\.js(?:\?v=[^"]*)?"[^>]*>' % f, h)
            self.assertEqual(tags, [t for t in tags if 'src="%s.js?v=%s"' % (f, SM.content_stamp(str(ROOT), f + '.js')) in t], f)
            self.assertEqual(len(tags), 1, (f, tags))
if __name__ == '__main__': unittest.main()
