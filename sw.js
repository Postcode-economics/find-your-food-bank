// Offline + traffic hardening (22 Oct 2026). App shell precached; static assets/data stale-while-revalidate (instant from cache,
// refreshed in the background); page itself network-first; shelters/warm spaces cached only once those layers are opened;
// OpenStreetMap tile URLs are cache-first, bounded to the 300 most recent, so a later visit still has a map with no network.
// fyfb-v93 (batch 3): v3.js carry-forward 'Not re-confirmed since' label (#235); v3.js ?v= hash recomputed (h419d69491af0).
// fyfb-v92 (batch 2): combined shell (layers.js, v3.js, v3.css) listed by ?v= hash, so the precache still changes.
// fyfb-v92: a loaded tile whose decode() rejects is not a tile failure. The build id bumps so phones self-heal.
// fyfb-v91: tile cache renamed fyfb-tiles2; the old fyfb-tiles store is deleted on activate.
// fyfb-v90: when this version takes over, MapTiler entries are deleted from the tile cache and are never served from it.
// OpenStreetMap tiles already in that cache stay.
const C='fyfb-v93',T='fyfb-tiles2',TMAX=300,SHELL=['./','index.html','data.js','stamp.js','access.js','layers.js','layers.js?v=hab3a40c10d4c','layers.css','layers.css?v=sh20261023','report.js','register.js','report.css','v3.js','v3.js?v=h419d69491af0','v3.css','v3.css?v=h3f31d4793dd2','icons.js','fb_secondary.png','privacy.html','terms.html','faq.html','accessibility.html','outcodes.json','counties.json','tiles.js','tiles.js?v=h5a2aeaaa2870','vendor/maptiler-logo.svg','vendor/leaflet.js','vendor/leaflet.css','vendor/leaflet.markercluster.js','vendor/MarkerCluster.css','vendor/MarkerCluster.Default.css','header.css?v=h7a3d7fe731ec'];
const TILE=/(^|\.)tile\.openstreetmap\.org$|^api\.maptiler\.com$|^tiles\.stadiamaps\.com$/;
const MAPTILER=/(^|\.)maptiler\.com$/;
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
// Self-heal (25 Oct 2026, Instagram in-app browser kept the old layout): on activate, drop old caches, take control and reload open map
// pages once, so a page served by an old worker/cached HTML comes back as the current build. Navigation always revalidates (no-cache).
// 25 Oct 11:29 live bug: navigating open pages from 'activate' left old-link visits (Instagram webview) blank/hung mid-load.
// Activate only drops old caches and takes control; stale pages are healed by the version check in index.html.
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C&&x!==T).map(x=>caches.delete(x))))
  .then(()=>caches.open(T)).then(async c=>{const ks=await c.keys();await Promise.all(ks.filter(r=>MAPTILER.test(new URL(r.url).host)).map(r=>c.delete(r)))})
  .then(()=>self.clients.claim()))});
const tell=()=>self.clients.matchAll().then(cs=>cs.forEach(c=>c.postMessage('offline')));
let trimming=false;const trim=c=>{if(trimming)return;trimming=true;c.keys().then(k=>Promise.all(k.slice(0,Math.max(0,k.length-TMAX)).map(r=>c.delete(r)))).finally(()=>{trimming=false})};
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET')return;
 if(TILE.test(u.host)){e.respondWith(caches.open(T).then(async c=>{
   if(MAPTILER.test(u.host)){const stale=await c.match(e.request);if(stale)c.delete(e.request);return fetch(e.request).then(r=>r).catch(()=>{tell();return Response.error()})}
   // fyfb-v91 (27 Oct 2026, iPhone outage): an opaque cached tile (stored for an <img>) is never served while online and only
   // readable (r.ok) responses are stored; it is never given to a CORS request. WebKit rejects it ("Response served by service worker is opaque"), so the tiles.js status probe goes
   // to the network instead and stores a readable copy. Offline, the probe fails and tiles.js shows the <img>,
   // which this cache still answers. The tile cache is renamed fyfb-tiles2 so activate drops the old opaque store.
   const hit=await c.match(e.request);if(hit&&hit.type!=='opaque')return hit;
   if(hit)c.delete(e.request);  // opaque copy (old builds): dropped and refetched; only kept as the offline answer below
   return fetch(e.request).then(r=>{if(r.ok){c.put(e.request,r.clone()).then(()=>trim(c))}return r}).catch(()=>{tell();return (hit&&e.request.mode!=='cors')?hit:Response.error()})}));return}
 if(/api\.postcodes\.io/.test(u.host)){e.respondWith(fetch(e.request).then(r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp))}return r})
   .catch(async()=>{tell();return (await caches.match(e.request))||Response.error()}));return}
 if(u.origin!==location.origin)return;
 if(/^\/(favicon\.ico|apple-touch-icon\.png|icon(-\d+)?\.(png|svg)|site\.webmanifest|sitemap\.xml|robots\.txt|version\.json)$/.test(u.pathname))return;  // icons, manifest, sitemap, robots: always straight from the network
 const put=r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp))}return r};
 if(/^\/(shelters|warmspaces|data|stamp|access)\.js$/.test(u.pathname)){const k=u.origin+u.pathname;  // shelters/warm spaces: network-first (a ?t= bucket gets past the CDN edge cache), one cache copy per file for offline
   e.respondWith(fetch(e.request).then(r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(k,cp))}return r}).catch(async()=>{tell();return (await caches.match(k))||Response.error()}));return}
 if(e.request.mode==='navigate'){e.respondWith(fetch(e.request.url,{cache:'no-cache',credentials:'same-origin'}).then(put).catch(async()=>{tell();return (await caches.match(e.request,{ignoreSearch:true}))||(/^\/(index\.html)?$/.test(u.pathname)?await caches.match('index.html'):null)||Response.error()}));return}  // area pages (/food-banks/...) never get the map shell
 e.respondWith(caches.match(e.request).then(hit=>{const net=fetch(e.request).then(put);
   if(hit){e.waitUntil(net.catch(()=>{}));return hit}
   return net.catch(async()=>{tell();return (await caches.match(e.request,{ignoreSearch:true}))||Response.error()})}))});
