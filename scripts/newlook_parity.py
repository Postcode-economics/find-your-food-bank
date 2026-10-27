import json,sys
from playwright.sync_api import sync_playwright
import check_browser as B
JS=r"""async()=>{
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const sig=c=>{const links=[...c.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')).sort();
 const txt=c.textContent.replace(/\s+/g,'');const rows=[...c.querySelectorAll('table tr')].map(r=>r.textContent.replace(/\s+/g,''));
 const rp=[...c.querySelectorAll('.rpb')].map(b=>b.dataset.rid||'');const btns=[...c.querySelectorAll('a,button')].length;
 return {links,txt,rows,rp,btns}};
const out={};const list=document.getElementById('list'),xe=document.getElementById('xextra')||document.body;
async function run(key,arr,html,host){out[key]={};for(let s=0;s<arr.length;s+=150){const els=arr.slice(s,s+150).map((i,n)=>{const d=document.createElement('div');d.className='card'+(key==='fb'?'':' x'+key);d.innerHTML=html(i);host.appendChild(d);return [i,d]});
 await sleep(250);for(const [i,d] of els){out[key][(i.id||i.name)+'|'+i.lat+'|'+i.lng]=sig(d);d.remove()}}}
await run('fb',items,i=>window.card(i,1.2),list);
for(const [k,src] of [['ws','WARMSPACES'],['sh','SHELTERS']])await run(k,(window[src]||{}).items||[],i=>window.__detail(k,i,1.2),xe);
return out}"""
def grab(port):
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path="/usr/bin/google-chrome");c=B.new_context(b,viewport={"width":390,"height":844});pg=c.new_page()
        def rt(route):
            r=route.fetch();t=r.text();i=t.index('\n})();')+1;route.fulfill(response=r,body=t[:i]+'window.__detail=detail;'+t[i:])
        pg.route('**/layers.js*',rt)
        B.stub_map_tiles(pg)  # page route is checked first; keep tiles on the placeholder
        B.goto(pg,f"http://127.0.0.1:{port}/?fresh=1");pg.wait_for_timeout(1500)
        for f in ("shelters.js","warmspaces.js"): pg.add_script_tag(url=f"http://127.0.0.1:{port}/{f}")
        pg.wait_for_timeout(800);r=pg.evaluate(JS);b.close();return r
a=grab(8766);b=grab(8765)
json.dump([a,b],open('/tmp/nl/parity_raw.json','w'))
for k in a: print(k,len(a[k]),len(b.get(k,{})))
