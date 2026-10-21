// Offline fallback: app shell + all three layers' data precached; network first, cache when offline. Map tiles cached as viewed.
const C='fyfb-v8',T='fyfb-tiles',SHELL=['./','index.html','data.js','shelters.js','warmspaces.js','layers.js','layers.css','report.js','register.js','report.css','v3.js','v3.css','icons.js','vendor/leaflet.js','vendor/leaflet.css','vendor/leaflet.markercluster.js','vendor/MarkerCluster.css','vendor/MarkerCluster.Default.css'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C&&x!==T).map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
const tell=()=>self.clients.matchAll().then(cs=>cs.forEach(c=>c.postMessage('offline')));
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET')return;
 if(/tile\.openstreetmap\.org/.test(u.host)){e.respondWith(caches.open(T).then(async c=>{const hit=await c.match(e.request);
   const net=fetch(e.request).then(r=>{if(r.ok||r.type==='opaque')c.put(e.request,r.clone());return r}).catch(()=>{tell();return hit||Response.error()});return hit||net}));return}
 if(u.origin!==location.origin&&!/api\.postcodes\.io/.test(u.host))return;
 e.respondWith(fetch(e.request).then(r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp))}return r})
  .catch(async()=>{tell();return (await caches.match(e.request,{ignoreSearch:u.origin===location.origin}))||Response.error()}))});
