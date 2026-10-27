/* Map tiles, in the order they are tried (Dean, 26 Oct 2026 17:07: OpenStreetMap by default, OpenFreeMap as the automatic backup).
   1. osm: OpenStreetMap raster tiles. The permanent default. No key.
   2. openfreemap: OpenFreeMap vector tiles (https://openfreemap.org). Free, no key, no usage limit. It only serves vector
      tiles, so MapLibre GL (vendor/maplibre-gl-csp.js + vendor/leaflet-maplibre-gl.js) is loaded only when the map switches
      to it. Style: positron (light). The light map is kept in dark mode too.
      Credit required by OpenFreeMap: "OpenFreeMap © OpenMapTiles Data from OpenStreetMap".
   3. maptiler: DISABLED future fallback. No key and no default. It is never tried while disabled is true,
      and a key alone does not enable it. Nothing promotes it on a date.
   Stadia is not used. Reorder nothing: tileCandidates() keeps OpenStreetMap first whatever order this array is in. */
window.TILE_PROVIDERS = [
  { name: 'osm', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>' },
  { name: 'openfreemap', type: 'vector', url: 'https://tiles.openfreemap.org/styles/positron', maxZoom: 19,
    attribution: '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> <a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">&copy; OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>' },
  { name: 'maptiler', key: '', disabled: true, url: 'https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key={key}', maxZoom: 19,
    attribution: '<a href="https://www.maptiler.com/copyright/" target="_blank" rel="noopener">&copy; MapTiler</a> <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">&copy; OpenStreetMap contributors</a>' }
];
/* How many of the last TILE_WINDOW tile attempts have to fail before leaving the current provider.
   Chrome still fires the image load event when a 401, 403 or 429 body is a valid PNG, so a tileerror
   counter never sees it: cached 200s and uncached 403s both look like successes. One fetch reads the
   status and its body is the picture (a data URL built in script, not a blob: URL). A second request
   for the same tile is what tipped OpenStreetMap into 429s. A fetch that throws with no status
   (iOS: "Response served by service worker is opaque") is not a failure; the plain <img> is the one
   request and only its own error counts.
   The check keeps running after the first load. */
window.TILE_WINDOW = 20;
window.TILE_WINDOW_FAILS = 4;
/* A 401, 403 or 429 (a refusal) switches only at TILE_WINDOW_REFUSALS in the window (Dean, 27 Oct 2026, from PR 169):
   phone networks and iCloud Private Relay share addresses, so one stray 429 must not drop the map. */
window.TILE_WINDOW_REFUSALS = 3;
window.tileCandidates = function () {
  var list = window.TILE_PROVIDERS.filter(function (p) {
    if (p.disabled) return false;
    return !/\{key\}/.test(p.url) || !!p.key;
  });
  var osm = [], rest = [];
  list.forEach(function (p) { (p.name === 'osm' ? osm : rest).push(p); });
  return osm.concat(rest);
};
/* MapLibre GL is ~1.4 MB, so it is fetched only when the map falls back to OpenFreeMap. */
window.loadVectorLib = function () {
  if (window._hmVectorLib) return window._hmVectorLib;
  function add(tag, attrs) {
    return new Promise(function (ok, bad) {
      var el = document.createElement(tag), k;
      for (k in attrs) el[k] = attrs[k];
      el.onload = ok; el.onerror = function () { bad(new Error('load ' + (attrs.src || attrs.href))); };
      document.head.appendChild(el);
    });
  }
  window._hmVectorLib = add('link', { rel: 'stylesheet', href: 'vendor/maplibre-gl.css' }).catch(function () {})
    .then(function () { return window.maplibregl ? null : add('script', { src: 'vendor/maplibre-gl-csp.js' }); })
    .then(function () {
      window.maplibregl.setWorkerUrl('vendor/maplibre-gl-csp-worker.js');
      return L.maplibreGL ? null : add('script', { src: 'vendor/leaflet-maplibre-gl.js' });
    });
  window._hmVectorLib.catch(function () { window._hmVectorLib = null; });
  return window._hmVectorLib;
};
window.addTiles = function (map) {
  if (map._hmTileStop) map._hmTileStop();
  var list = window.tileCandidates(), gen = 0, layer = null, logoCtl = null, vectorFailed = false;
  /* Freeze fix (Dean's iPhone, 27 Oct 2026, from PR 186): Leaflet takes the map's max zoom from its layers. The OpenFreeMap
     (MapLibre) layer does not register one, and while it loads there is no tile layer at all, so getMaxZoom() was
     Infinity. The marker cluster's clearLayers() then rebuilds clusters for every zoom from Infinity down, a loop
     that never ends: the first filter tap froze the page. Pin the map's own max zoom so it is always finite. */
  if (map.options.maxZoom === undefined) map.setMaxZoom(Math.max.apply(null, list.map(function (p) { return p.maxZoom || 19; })));
  window.TILE_ORDER = list.map(function (p) { return p.name; });
  function providerUrl(p) {
    var url = p.url;
    if (p.key && url.indexOf('{key}') >= 0) url = url.replace('{key}', encodeURIComponent(p.key));
    return url;
  }
  function logo(on) {
    if (on && !logoCtl) {
      logoCtl = L.control({ position: 'bottomleft' });
      logoCtl.onAdd = function () {
        var a = L.DomUtil.create('a', 'maptiler-logo');
        a.href = 'https://www.maptiler.com/'; a.target = '_blank'; a.rel = 'noopener';
        a.setAttribute('aria-label', 'MapTiler');
        a.innerHTML = '<img src="vendor/maptiler-logo.svg" alt="MapTiler logo" width="80" height="24" style="display:block">';
        return a;
      };
      logoCtl.addTo(map);
    } else if (!on && logoCtl) { map.removeControl(logoCtl); logoCtl = null; }
  }
  function use(i) {
    var my = ++gen, p = list[i];
    if (layer) { map.removeLayer(layer); layer = null; }
    if (!p) return;
    if (p.type === 'vector') { useVector(p, my, i); return; }
    var n = i, switched = false, used = 0, ok = 0, bad = 0, recent = [], codes = [];
    window.TILE_STATS = window.TILE_STATS || {load: 0, error: 0, probe: 0};
    /* recent holds 1 for a success, 0 for an error, 2 for a refusal (401, 403, 429). */
    function note(success, refused) {
      if (success) ok++; else bad++;
      recent.push(success ? 1 : (refused ? 2 : 0));
      var limit = window.TILE_WINDOW || 20;
      if (recent.length > limit) recent.shift();
      var windowBad = 0, k;
      for (k = 0; k < recent.length; k++) if (recent[k] !== 1) windowBad++;
      return windowBad;
    }
    function refusals() {
      var c = 0, k;
      for (k = 0; k < recent.length; k++) if (recent[k] === 2) c++;
      return c;
    }
    /* The phone is offline: a failed tile says nothing about the provider, so it is not counted. */
    function offline() { return navigator.onLine === false; }
    function giveUp(reason) {
      if (switched || my !== gen || n >= list.length - 1) return;
      /* OpenFreeMap already failed to load this visit: stay on OpenStreetMap, never loop back to a blank map. */
      if (vectorFailed && list[n + 1].type === 'vector') return;
      switched = true;
      var windowBad = 0, k;
      for (k = 0; k < recent.length; k++) if (recent[k] !== 1) windowBad++;
      window.TILE_FAILOVER = { from: p.name, to: list[n + 1].name, ok: ok, bad: bad, windowBad: windowBad, refused: refusals(), reason: String(reason), codes: codes.slice(-10) };
      use(n + 1);
    }
    var Layer = L.TileLayer.extend({
      createTile: function (coords, done) {
        var img = document.createElement('img'), size = this.getTileSize();
        img.alt = ''; img.width = size.x; img.height = size.y;
        if (p.cap && used >= p.cap) { done(null, img); return img; }
        if (p.cap) used++;
        /* No crossOrigin (27 Oct 2026, iPhone outage). crossorigin="anonymous" makes the <img> a CORS
           request, and WebKit then refuses the opaque tile the service worker stored for a normal image. */
        img.referrerPolicy = 'strict-origin-when-cross-origin';
        var url = this.getTileUrl(coords), tileGen = my, shown = false, counted = false;
        /* data-tile is the real tile URL. img.src is a data URL of the one fetch, or the tile URL
           itself when that fetch threw and the <img> is the request. Offline checks read either.
           A blob: URL is a second request. WebKit's FileReader reads a blob that way, and a check
           that aborts unknown URLs then counts a good tile as a failure. */
        img.setAttribute('data-tile', url);
        var ac = typeof AbortController === 'function' ? new AbortController() : null;
        function dead() { return tileGen !== gen || (ac && ac.signal.aborted); }
        function drop() { if (ac) { try { ac.abort(); } catch (e) {} } }
        img._hmAbort = drop;
        function countOk() {
          if (counted || dead()) return;
          counted = true;
          window.TILE_STATS.load++;
          note(true);  /* a success never switches the map */
        }
        function countBad(refused, why) {
          if (dead()) return;
          window.TILE_STATS.error++;
          codes.push(why);
          done(new Error(String(why)), img);
          if (offline()) return;
          var errs = note(false, !!refused);
          if (refused && refusals() >= (window.TILE_WINDOW_REFUSALS || 3)) giveUp(why);
          else if (errs >= (window.TILE_WINDOW_FAILS || 4)) giveUp('errors');
        }
        function reveal() {
          /* Fetch threw with no HTTP status, even after the retry. Not a tile failure. The <img> is
             the one request: if it really cannot load, its onerror counts the failure. */
          if (shown || dead()) return;
          shown = true;
          img.onload = function () {
            if (dead()) return;
            countOk();
            done(null, img);
          };
          img.onerror = function () {
            if (tileGen !== gen || (ac && ac.signal.aborted)) return;
            countBad(false, 'decode');
          };
          img.src = url;
        }
        function paint(buf, mime) {
          if (dead()) return;
          /* Build the data URL here. A blob URL, and FileReader which reads one, is a second
             request, and a check that aborts unknown URLs then counts a good tile as a failure. */
          var bytes = new Uint8Array(buf), parts = [], i, step = 8192;
          for (i = 0; i < bytes.length; i += step) parts.push(String.fromCharCode.apply(null, bytes.subarray(i, i + step)));
          img.onload = function () {
            if (dead()) return;
            done(null, img);
          };
          img.onerror = function () {
            if (tileGen !== gen || (ac && ac.signal.aborted)) return;
            countBad(false, 'decode');
          };
          img.src = 'data:' + String(mime || 'image/png').split(';')[0] + ';base64,' + btoa(parts.join(''));
        }
        /* A fetch that fails outright (no HTTP status, e.g. iOS 'Load failed' on a network change) is tried
           once more. HTTP statuses are never retried. credentials omit, referrer is the origin (OSM tile
           policy) and no extra headers: a simple GET, no preflight, no second download of a tile that loaded. */
        function get(retried) {
          var opts = {credentials: 'omit', referrerPolicy: 'strict-origin-when-cross-origin'};
          if (ac) opts.signal = ac.signal;
          return fetch(url, opts).catch(function (e) {
            if ((ac && ac.signal.aborted) || (e && e.name === 'AbortError') || retried || tileGen !== gen) throw e;
            window.TILE_STATS.retry = (window.TILE_STATS.retry || 0) + 1;
            return new Promise(function (r) { setTimeout(r, 400); }).then(function () {
              if ((ac && ac.signal.aborted) || tileGen !== gen) throw e;
              return get(true);
            });
          });
        }
        /* Wait until this turn's view changes have aborted tiles that will never be shown (Locate fits
           twice back to back). Otherwise the first grid is already on the wire. */
        var start = window.queueMicrotask || function (fn) { setTimeout(fn, 0); };
        start(function () {
          if (dead()) return;
          window.TILE_STATS.probe++;
          get(false).then(function (r) {
            if (dead()) return;
            /* Read the body before counting. Switching aborts every in-flight tile fetch, and
               aborting this response before the body arrives hides a PNG 403 from the page. */
            if (r.status === 401 || r.status === 403 || r.status === 429 || !r.ok) {
              var refused = r.status === 401 || r.status === 403 || r.status === 429;
              var why = refused ? r.status : (r.status || 'tile');
              var read = r.arrayBuffer ? r.arrayBuffer().catch(function () {}) : Promise.resolve();
              return read.then(function () { if (!dead()) countBad(refused, why); });
            }
            countOk();
            var mime = (r.headers && r.headers.get && r.headers.get('content-type')) || 'image/png';
            return r.arrayBuffer().then(function (buf) { paint(buf, mime); }, function () { if (!dead()) countBad(false, 'decode'); });
          }, function (e) {
            /* No HTTP status, even after the retry: WebKit "Response served by service worker is opaque",
               or the network. Not a tile failure. The <img> loads the tile once. */
            if ((ac && ac.signal.aborted) || (e && e.name === 'AbortError') || tileGen !== gen) return;
            window.TILE_STATS.probeOpaque = (window.TILE_STATS.probeOpaque || 0) + 1;
            codes.push('probe-opaque');
            reveal();
          });
        });
        return img;
      }
    });
    /* updateWhenZooming stays false: Leaflet flyTo, and a zoom animation with the default, requests a
       full grid at every integer zoom on the way. Locate crosses several levels; those grids are the
       429s. Tiles already on screen scale, and one grid loads when the view settles. keepBuffer stays
       2 because it only keeps tiles already fetched across a small pan. It does not prefetch, and
       lowering it would refetch the same edge on the way back. */
    layer = new Layer(providerUrl(p), { maxZoom: p.maxZoom || 19, attribution: p.attribution, updateWhenZooming: false, keepBuffer: 2 });
    layer.on('tileabort tileunload', function (e) { if (e.tile && e.tile._hmAbort) e.tile._hmAbort(); });
    layer.addTo(map);
    window.TILE_ACTIVE = p.name;
    logo(p.name === 'maptiler');
  }
  /* OpenFreeMap: a MapLibre GL layer inside Leaflet. Markers, clusters and controls are unchanged. */
  function useVector(p, my, i) {
    window.TILE_ACTIVE = p.name; logo(false);
    /* Any OpenFreeMap failure (script load, no WebGL e.g. iOS Lockdown Mode, MapLibre setup throwing) goes back
       to OpenStreetMap, never a blank map. vectorFailed allows that once per page: giveUp then never returns to
       OpenFreeMap, so there is no flip-flop. */
    function fail(e) {
      if (my !== gen) return;
      if (layer) { try { map.removeLayer(layer); } catch (x) {} layer = null; }
      window.TILE_VECTOR = 'failed: ' + (e && e.message);
      if (i < list.length - 1) { use(i + 1); return; }
      if (!vectorFailed && list[0] && list[0].type !== 'vector') {
        vectorFailed = true;
        if (window.TILE_FAILOVER) window.TILE_FAILOVER.back = list[0].name;
        use(0);
      }
    }
    window.loadVectorLib().then(function () {
      if (my !== gen) return;
      var gl = window.maplibregl;
      if (gl && typeof gl.supported === 'function' && !gl.supported()) throw new Error('webgl unsupported');
      if (!gl || typeof gl.supported !== 'function') {
        var cv = document.createElement('canvas');
        if (!(cv.getContext('webgl2') || cv.getContext('webgl'))) throw new Error('webgl unsupported');
      }
      layer = L.maplibreGL({ style: p.url, maxZoom: p.maxZoom || 19, pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
        attributionControl: { customAttribution: p.attribution } });
      layer.addTo(map);
      window.TILE_VECTOR = 'ready';
    }).catch(fail);
  }
  map._hmTileStop = function () {
    gen++;
    if (layer) { map.removeLayer(layer); layer = null; }
    if (logoCtl) { map.removeControl(logoCtl); logoCtl = null; }
  };
  use(0);
  if (/[?&]tiles=debug(&|$)/.test(location.search)) debugReadout(map);
  return layer;
};

/* ?tiles=debug only: plain text under the map credit naming the active map, and why it switched if it did.
   Without the flag nothing is added. */
function debugReadout(map) {
  if (map._hmDebugCtl) map.removeControl(map._hmDebugCtl);
  var ctl = L.control({ position: 'bottomright' }), box;
  map._hmDebugCtl = ctl;
  ctl.onAdd = function () {
    box = L.DomUtil.create('div', 'tiles-debug');
    box.id = 'tiles-debug';
    box.style.cssText = 'background:#fff;color:#000;font:12px/1.3 monospace;padding:2px 4px;margin:0;max-width:60vw;white-space:pre-wrap';
    return box;
  };
  ctl.addTo(map);
  function draw() {
    var fo = window.TILE_FAILOVER, st = window.TILE_STATS || {};
    var t = 'map: ' + window.TILE_ACTIVE + ' | loaded ' + (st.load || 0) + ', errors ' + (st.error || 0) + ', retries ' + (st.retry || 0);
    t += fo ? '\nswitched ' + fo.from + '->' + fo.to + ': reason ' + fo.reason + ', failures ' + fo.bad + ' (' + fo.windowBad + ' of last 20), ok ' + fo.ok + ', codes ' + (fo.codes || []).join(',') + (fo.back ? ', back to ' + fo.back : '') : '\nno switch';
    if (box.textContent !== t) box.textContent = t;
  }
  draw();
  /* One timer per page: a re-run of addTiles replaces the old readout instead of stacking timers. */
  if (window._hmTilesDebugTimer) clearInterval(window._hmTilesDebugTimer);
  window._hmTilesDebugTimer = setInterval(draw, 1000);
}
