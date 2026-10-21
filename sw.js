// Offline fallback: app shell + each layer's data cached; network first, cache when offline.
const C='fyfb-v1',SHELL=['./','index.html','data.js','layers.js','layers.css','vendor/leaflet.js','vendor/leaflet.css','vendor/leaflet.markercluster.js','vendor/MarkerCluster.css','vendor/MarkerCluster.Default.css'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C&&x!=='fyfb-tiles').map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET')return;
 if(/tile\.openstreetmap\.org/.test(u.host)){e.respondWith(caches.open('fyfb-tiles').then(async c=>{const hit=await c.match(e.request);
   const net=fetch(e.request).then(r=>{if(r.ok||r.type==='opaque')c.put(e.request,r.clone());return r}).catch(()=>hit);return hit||net}));return}
 if(u.origin!==location.origin&&!/api\.postcodes\.io/.test(u.host))return;
 e.respondWith(fetch(e.request).then(r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp))}return r}).catch(()=>caches.match(e.request,{ignoreSearch:u.origin===location.origin})))});
