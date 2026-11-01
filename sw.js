// Offline + traffic hardening (22 Oct 2026). App shell precached; static assets/data stale-while-revalidate (instant from cache,
// refreshed in the background); page itself network-first; shelters/warm spaces cached only once those layers are opened;
// OpenStreetMap tile URLs are cache-first, bounded to the 300 most recent, so a later visit still has a map with no network.
// fyfb-v96: tiles.js remembers painted tiles and fetches the next zoom-out ahead, so zooming out paints with no grey.
//   layers.js and tiles.js get tags the live site was never asked for (Cloudflare held old copies under the earlier ones).
// fyfb-v95: OSM tiles are cached and matched by the URL string, so a CORS probe and a no-cors <img> share one entry.
// The worker registers from the document head and claims the page on load (clients.claim), so a pan is served from
// the tile cache. The next visit is controlled from the first request.
// fyfb-v94 (batch 4): stamped data/stamp/access cache-first; OSM <img> tiles fetched in cors mode and deduped in flight.
// fyfb-v93 (batch 3 on batch 1): v3.js carry-forward 'Not re-confirmed since' label (#235); v3.js and header.css ?v= hashes recomputed.
// fyfb-v92 (batch 2): combined shell (layers.js, v3.js, v3.css) listed by ?v= hash, so the precache still changes.
// fyfb-v92: a loaded tile whose decode() rejects is not a tile failure. The build id bumps so phones self-heal.
// fyfb-v91: tile cache renamed fyfb-tiles2; the old fyfb-tiles store is deleted on activate.
// fyfb-v90: when this version takes over, MapTiler entries are deleted from the tile cache and are never served from it.
// OpenStreetMap tiles already in that cache stay.
const C='fyfb-v96',T='fyfb-tiles2',TMAX=300,SHELL=['./','index.html','data.js','stamp.js','access.js','facts.js','facts.js?v=h25f26f924c18','layers.js','layers.js?v=hb738873e0d3f','layers.css','layers.css?v=h2e7bf96289eb','report.js','register.js','report.css','v3.js','v3.js?v=hcc7d4cda4d2d','v3.css','v3.css?v=hdae3009fa20c','icons.js','fb_secondary.png','privacy.html','terms.html','faq.html','accessibility.html','outcodes.json','counties.json','tiles.js','tiles.js?v=h8e7e4a0c5e68','vendor/maptiler-logo.svg','vendor/leaflet.js','vendor/leaflet.css','vendor/leaflet.markercluster.js','vendor/leaflet.markercluster.js?v=hc3b59fe18416','vendor/MarkerCluster.css','vendor/MarkerCluster.Default.css','header.css?v=h3a2ad6b9d92c'];
const TILE=/(^|\.)tile\.openstreetmap\.org$|^api\.maptiler\.com$/;
// OpenFreeMap backup (27 Oct 2026): versioned tiles, fonts and sprites are cache-first; style and TileJSON are network-first with the cached copy offline.
const OFM=/^tiles\.openfreemap\.org$/,OFM_FIXED=/^\/(planet\/\d{8}_[^/]+\/|fonts\/|sprites\/ofm_f384\/|natural_earth\/)/;
const MAPTILER=/(^|\.)maptiler\.com$/;
// Precache, but do not skipWaiting until the page asks (message 'hm-claim', sent on load). Activating during
// install took tile requests before the map had painted; a pan after load is then served from this cache, and the
// next visit is controlled from the first request.
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)))});
self.addEventListener('message',e=>{if(e.data==='hm-claim')self.skipWaiting()});
// Self-heal (25 Oct 2026, Instagram in-app browser kept the old layout): on activate, drop old caches, take control and reload open map
// pages once, so a page served by an old worker/cached HTML comes back as the current build. Navigation always revalidates (no-cache).
// 25 Oct 11:29 live bug: navigating open pages from 'activate' left old-link visits (Instagram webview) blank/hung mid-load.
// Activate only drops old caches and takes control; stale pages are healed by the version check in index.html.
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C&&x!==T).map(x=>caches.delete(x))))
  .then(()=>caches.open(T)).then(async c=>{const ks=await c.keys();await Promise.all(ks.filter(r=>MAPTILER.test(new URL(r.url).host)).map(r=>c.delete(r)))})
  .then(()=>self.clients.claim()))});
const tileNet=new Map();  // tile URL -> promise of "stored" for a tile fetch still in flight
const tell=()=>self.clients.matchAll().then(cs=>cs.forEach(c=>c.postMessage('offline')));
let trimming=false;const trim=c=>{if(trimming)return;trimming=true;c.keys().then(k=>Promise.all(k.slice(0,Math.max(0,k.length-TMAX)).map(r=>c.delete(r)))).finally(()=>{trimming=false})};
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET')return;
 if(OFM.test(u.host)){e.respondWith(caches.open(T).then(async c=>{const keep=r=>{if(r.ok){c.put(e.request,r.clone()).then(()=>trim(c))}return r};
   if(OFM_FIXED.test(u.pathname)){const got=await c.match(e.request);if(got)return got;return fetch(e.request).then(keep).catch(()=>{tell();return Response.error()})}
   return fetch(e.request).then(keep).catch(async()=>{tell();return (await c.match(e.request))||Response.error()})}));return}
 if(TILE.test(u.host)){e.respondWith(caches.open(T).then(async c=>{
   if(MAPTILER.test(u.host)){const stale=await c.match(e.request);if(stale)c.delete(e.request);return fetch(e.request).then(r=>r).catch(()=>{tell();return Response.error()})}
   // fyfb-v91 (27 Oct 2026, iPhone outage): an opaque cached tile (stored for an <img>) is never served while online and only
   // readable (r.ok) responses are stored; it is never given to a CORS request. WebKit rejects it ("Response served by service worker is opaque"), so the tiles.js status probe goes
   // to the network instead and stores a readable copy. Offline, the probe fails and tiles.js shows the <img>,
   // which this cache still answers. The tile cache is renamed fyfb-tiles2 so activate drops the old opaque store.
   const url=e.request.url;
   const hit=await c.match(url);if(hit&&hit.type!=='opaque')return hit;
   if(hit)c.delete(url);  // opaque copy (old builds): dropped and refetched; only kept as the offline answer below
   // Batch 4 (27 Oct 2026): an <img> tile request is no-cors, so its answer is opaque and was never stored: repeat visits
   // always went to the network. OpenStreetMap sends Access-Control-Allow-Origin: *, so the worker fetches the same URL
   // in cors mode instead; the readable copy is stored and answers both the <img> and the tiles.js probe next time.
   // tiles.js reveals the <img> as soon as the probe's headers arrive, before that copy is stored: a request for a tile
   // already on its way waits for the stored copy instead of fetching the same tile again (one network request per tile).
   const busy=tileNet.get(url);if(busy&&await busy){const got=await c.match(url);if(got)return got}
   let fin;const saved=new Promise(r=>{fin=r});if(!busy){tileNet.set(url,saved);saved.then(()=>tileNet.delete(url))}
   return fetch(e.request.mode==='no-cors'&&e.request.destination==='image'?new Request(url,{mode:'cors',credentials:'omit'}):e.request).catch(()=>fetch(e.request)).then(r=>{if(r.ok){c.put(url,r.clone()).then(()=>{fin(true);trim(c)},()=>fin(false))}else fin(false);return r}).catch(()=>{fin(false);tell();return (hit&&e.request.mode!=='cors')?hit:Response.error()})}));return}
 if(/api\.postcodes\.io/.test(u.host)){e.respondWith(fetch(e.request).then(r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp))}return r})
   .catch(async()=>{tell();return (await caches.match(e.request))||Response.error()}));return}
 if(u.origin!==location.origin)return;
 if(/^\/(favicon\.ico|apple-touch-icon\.png|icon(-\d+)?\.(png|svg)|site\.webmanifest|sitemap\.xml|robots\.txt|version\.json)$/.test(u.pathname))return;  // icons, manifest, sitemap, robots: always straight from the network
 // Batch 4 (27 Oct 2026): data/stamp/access with a ?v=h<content hash> stamp are cache-first. The stamp is the file's own
 // hash (seo_meta.content_stamp) and the HTML that names it is network-first, so a cached copy can never be an old one.
 // Older stamped copies of the same file are dropped when a new one is saved. Unstamped requests stay network-first.
 if(/^\/(data|stamp|access)\.js$/.test(u.pathname)&&/(^|&)v=h[0-9a-f]{12}(&|$)/.test(u.search.slice(1))){const k=u.origin+u.pathname;e.respondWith(caches.open(C).then(async c=>{const hit=await c.match(e.request.url);if(hit)return hit;
     return fetch(e.request).then(async r=>{if(r.ok){const a=r.clone(),b=r.clone();const ks=await c.keys();await Promise.all(ks.filter(q=>{const x=new URL(q.url);return x.pathname===u.pathname&&x.search&&q.url!==e.request.url}).map(q=>c.delete(q)));await c.put(e.request.url,a);await c.put(k,b)}return r})
       .catch(async()=>{tell();return (await c.match(k))||Response.error()})}));return}
 const put=r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(e.request,cp))}return r};
 if(/^\/(shelters|warmspaces|data|stamp|access)\.js$/.test(u.pathname)){const k=u.origin+u.pathname;  // shelters/warm spaces: network-first (a ?t= bucket gets past the CDN edge cache), one cache copy per file for offline
   e.respondWith(fetch(new Request(e.request,{cache:'no-cache'})).then(r=>{if(r.ok){const cp=r.clone();caches.open(C).then(c=>c.put(k,cp))}return r}).catch(async()=>{tell();return (await caches.match(k))||Response.error()}));return}
 if(e.request.mode==='navigate'){const home=/^\/(index\.html)?$/.test(u.pathname);  // the map page is also saved as the shell, so offline always opens the newest copy seen
   e.respondWith(fetch(e.request.url,{cache:'no-cache',credentials:'same-origin'}).then(r=>{if(r.ok&&home){const cp=r.clone();caches.open(C).then(c=>Promise.all([c.put(u.origin+'/',cp.clone()),c.put(u.origin+'/index.html',cp)]))}return put(r)}).catch(async()=>{tell();return (await caches.match(e.request))||(home?await caches.match(u.origin+'/'):null)||(await caches.match(e.request,{ignoreSearch:true}))||(/^\/(index\.html)?$/.test(u.pathname)?await caches.match('index.html'):null)||Response.error()}));return}  // area pages (/food-banks/...) never get the map shell
 // Freshness (26 Oct 2026, Dean): a returning visitor must never get an old copy after a deploy. Only files with a ?v= version
 // stamp are served cache-first (a new deploy changes the stamp, so a cached copy can never be stale). Everything else on this
 // site (pages, data, JSON, unstamped scripts and styles) is network-first, revalidated past the HTTP cache, with the saved copy
 // used only when the network fails (offline mode keeps working).
 if(/(^|&)v=/.test(u.search.slice(1))){e.respondWith(caches.match(e.request).then(hit=>hit||fetch(e.request).then(put).catch(async()=>{tell();return (await caches.match(e.request,{ignoreSearch:true}))||Response.error()})));return}
 e.respondWith(fetch(new Request(e.request,{cache:'no-cache'})).then(put).catch(async()=>{tell();return (await caches.match(e.request))||(await caches.match(e.request,{ignoreSearch:true}))||Response.error()}))});
