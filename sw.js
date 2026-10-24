// Offline + traffic hardening (22 Oct 2026). App shell precached; static assets/data stale-while-revalidate (instant from cache,
// refreshed in the background); page itself network-first; shelters/warm spaces cached only once those layers are opened;
// map tiles (any provider in tiles.js) cache-first, bounded to the 300 most recent.
const C='fyfb-v71',T='fyfb-tiles',TMAX=300,SHELL=['./','index.html','data.js','stamp.js','access.js','layers.js','layers.js?v=nl20261024b','layers.css','layers.css?v=sh20261023','report.js','register.js','report.css','v3.js','v3.js?v=ux20261023f','v3.css','v3.css?v=nl20261024c','icons.js','fb_secondary.png','privacy.html','terms.html','faq.html','accessibility.html','outcodes.json','tiles.js','vendor/maptiler-logo.svg','vendor/leaflet.js','vendor/leaflet.css','vendor/leaflet.markercluster.js','vendor/MarkerCluster.css','vendor/MarkerCluster.Default.css'];
const TILE=/(^|\.)tile\.openstreetmap\.org$|^api\.maptiler\.com$|^tiles\.stadiamaps\.com$/;
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C&&x!==T).map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
const tell=()=>self.clients.matchAll().then(cs=>cs.forEach(c=>c.postMessage('offline')));
let trimming=false;const trim=c=>{if(trimming)return;trimming=true;c.keys().then(k=>Promise.all(k.slice(0,Math.max(0,k.length-TMAX)).map(r=>c.delete(r)))).finally(()=>{trimming=false})};
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET')return;
 if(TILE.test(u.host)){e.respondWith(caches.open(T).then(async c=>{const hit=await c.match(e.request);if(hit)return hit;
   return fetch(e.request).then(r=>{if(r.ok||r.type==='opaque'){c.put(e.request,r.clone()).then(()=>trim(c))}return r}).catch(()=>{tell();return Response.error()})}));return}
 if(/api\.postcodes\.io/.test(u.host)){e.respondWith(fetch(e.request).then(r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp))}return r})
   .catch(async()=>{tell();return (await caches.match(e.request))||Response.error()}));return}
 if(u.origin!==location.origin)return;
 if(/^\/(favicon\.ico|apple-touch-icon\.png|icon(-\d+)?\.(png|svg)|site\.webmanifest|sitemap\.xml|robots\.txt)$/.test(u.pathname))return;  // icons, manifest, sitemap, robots: always straight from the network
 const put=r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp))}return r};
 if(/^\/(shelters|warmspaces|data|stamp|access)\.js$/.test(u.pathname)){const k=u.origin+u.pathname;  // shelters/warm spaces: network-first (a ?t= bucket gets past the CDN edge cache), one cache copy per file for offline
   e.respondWith(fetch(e.request).then(r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(k,cp))}return r}).catch(async()=>{tell();return (await caches.match(k))||Response.error()}));return}
 if(e.request.mode==='navigate'){e.respondWith(fetch(e.request).then(put).catch(async()=>{tell();return (await caches.match(e.request,{ignoreSearch:true}))||(/^\/(index\.html)?$/.test(u.pathname)?await caches.match('index.html'):null)||Response.error()}));return}  // area pages (/food-banks/...) never get the map shell
 e.respondWith(caches.match(e.request).then(hit=>{const net=fetch(e.request).then(put);
   if(hit){e.waitUntil(net.catch(()=>{}));return hit}
   return net.catch(async()=>{tell();return (await caches.match(e.request,{ignoreSearch:true}))||Response.error()})}))});
