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
   A 401, 403 or 429 switches on its own. Chrome still fires the image load event when that
   response body is a valid PNG, so a tileerror counter never sees it: cached 200s and uncached
   403s both look like successes. The status is read from the tile fetch, not from the image event.
   A probe that throws with no status (iOS: "Response served by service worker is opaque") is not a
   failure; the plain <img> is shown and only its own error counts. The check keeps running after the first load. */
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
      /* Absolute worker URL. WebKit throws "The string did not match the expected pattern" for
         new Worker('') or a relative worker URL that does not resolve (older iOS / WKWebView). */
      window.maplibregl.setWorkerUrl(new URL('vendor/maplibre-gl-csp-worker.js', location.href).href);
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
        function reveal() {
          if (shown || tileGen !== gen) return;
          shown = true;
          img.onload = function () {
            if (tileGen !== gen) return;
            if (!counted) {
              counted = true;
              window.TILE_STATS.load++;
              note(true);  /* a success never switches the map */
            }
            done(null, img);
          };
          img.onerror = function () {
            if (tileGen !== gen) return;
            window.TILE_STATS.error++;
            codes.push('decode');
            done(new Error('decode'), img);
            if (offline()) return;
            var failed = note(false);
            if (failed >= (window.TILE_WINDOW_FAILS || 4)) giveUp('errors');
          };
          img.src = url;
        }
        window.TILE_STATS.probe++;
        /* A fetch that fails outright (no HTTP status, e.g. iOS 'Load failed' on a network change) is tried
           once more. HTTP statuses are never retried. credentials omit and no extra headers: a simple GET,
           no preflight. */
        function get(retried) {
          return fetch(url, {credentials: 'omit'}).catch(function (e) {
            if (retried || tileGen !== gen) throw e;
            window.TILE_STATS.retry = (window.TILE_STATS.retry || 0) + 1;
            return new Promise(function (r) { setTimeout(r, 400); }).then(function () { return get(true); });
          });
        }
        get(false).then(function (r) {
          if (tileGen !== gen) return;
          if (!r.ok) codes.push(r.status);
          if (r.status === 401 || r.status === 403 || r.status === 429) {
            window.TILE_STATS.error++;
            done(new Error(String(r.status)), img);
            if (offline()) return;
            var errs = note(false, true);
            if (refusals() >= (window.TILE_WINDOW_REFUSALS || 3)) giveUp(r.status);
            else if (errs >= (window.TILE_WINDOW_FAILS || 4)) giveUp('errors');
            return;
          }
          if (!r.ok) {
            window.TILE_STATS.error++;
            done(new Error(String(r.status || 'tile')), img);
            if (offline()) return;
            var missed = note(false);
            if (missed >= (window.TILE_WINDOW_FAILS || 4)) giveUp('errors');
            return;
          }
          if (!counted) {
            counted = true;
            window.TILE_STATS.load++;
            note(true);  /* a success never switches the map */
          }
          /* The status is known. The image uses the real tile URL (offline checks read img.src). */
          reveal();
        }, function () {
          /* The probe threw with no HTTP status, even after the retry: WebKit "Response served by service
             worker is opaque", or the network. That is not a tile failure. The <img> is the map: if it
             really cannot load, its onerror counts the failure. */
          if (tileGen !== gen) return;
          window.TILE_STATS.probeOpaque = (window.TILE_STATS.probeOpaque || 0) + 1;
          codes.push('probe-opaque');
          reveal();
        });
        return img;
      }
    });
    layer = new Layer(providerUrl(p), { maxZoom: p.maxZoom || 19, attribution: p.attribution });
    layer.addTo(map);
    window.TILE_ACTIVE = p.name;
    logo(p.name === 'maptiler');
  }
  /* Phones get pixel ratio 1. iPhone 13 is devicePixelRatio 3; a ratio of 2 still builds a canvas
     about 2.4× the map (Leaflet padding included) and iOS drops the only WebGL context while it is created. */
  function vectorPixelRatio() {
    var dpr = window.devicePixelRatio || 1, phone = false;
    try {
      var coarse = window.matchMedia && window.matchMedia('(hover: none) and (pointer: coarse)').matches;
      phone = !!(coarse || (navigator.maxTouchPoints >= 1) || /iPhone|iPad|iPod/i.test(navigator.userAgent || ''));
    } catch (e) {}
    return Math.min(dpr, phone ? 1 : 2);
  }
  /* This MapLibre build does not export maplibregl.supported. The probe context is released at once:
     iOS allows only a handful of WebGL contexts, and a leaked probe makes the real map lose its context
     on the first frame (canvas exists, no tiles, and the page never falls back). */
  function webglOk() {
    var gl = window.maplibregl;
    if (gl && typeof gl.supported === 'function') return !!gl.supported();
    var cv = document.createElement('canvas'), ctx = null;
    try { ctx = cv.getContext('webgl2') || cv.getContext('webgl'); } catch (e) { ctx = null; }
    if (!ctx) return false;
    try {
      var lose = ctx.getExtension && ctx.getExtension('WEBGL_lose_context');
      if (lose) lose.loseContext();
    } catch (e) {}
    cv.width = 0; cv.height = 0;
    return true;
  }
  /* OpenFreeMap: a MapLibre GL layer inside Leaflet. Markers, clusters and controls are unchanged. */
  function useVector(p, my, i) {
    window.TILE_ACTIVE = p.name; logo(false);
    /* Any OpenFreeMap failure (script load, no WebGL e.g. iOS Lockdown Mode, MapLibre setup throwing,
       a style that never loads, or a WebGL context that stays lost) goes back to OpenStreetMap, never a
       blank map. vectorFailed allows that once per page: giveUp then never returns to OpenFreeMap, so
       there is no flip-flop. The 3-in-20 refusal rule is unchanged; this only covers the vector layer. */
    var settled = false, watch = null;
    function fail(e) {
      if (settled || my !== gen) return;
      settled = true;
      if (watch) { clearTimeout(watch); watch = null; }
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
      /* Let a tap that arrived while the script was parsing run before WebGL setup. */
      return new Promise(function (ok) { setTimeout(ok, 0); });
    }).then(function () {
      if (my !== gen) return;
      if (!webglOk()) throw new Error('webgl unsupported');
      layer = L.maplibreGL({ style: p.url, maxZoom: p.maxZoom || 19, pixelRatio: vectorPixelRatio(),
        trackResize: false, attributionControl: { customAttribution: p.attribution } });
      layer.addTo(map);
      var glMap = layer.getMaplibreMap();
      var canvas = layer.getCanvas(), lost = 0, restored = true;
      watch = setTimeout(function () {
        if (my !== gen || settled) return;
        if (!glMap.isStyleLoaded || !glMap.isStyleLoaded()) fail(new Error('vector style timeout'));
      }, 6000);
      glMap.on('load', function () {
        if (my !== gen || settled) return;
        if (watch) { clearTimeout(watch); watch = null; }
        window.TILE_VECTOR = 'ready';
      });
      /* A style or worker error before the style loads used to leave TILE_VECTOR 'ready' on an empty canvas.
         Tile errors after the style has loaded stay on this provider (the 3-in-20 rule is for OSM). */
      glMap.on('error', function (ev) {
        if (my !== gen || settled) return;
        if (glMap.isStyleLoaded && glMap.isStyleLoaded()) return;
        var err = ev && ev.error;
        fail(err || new Error('vector error'));
      });
      if (canvas) {
        canvas.addEventListener('webglcontextlost', function (ev) {
          if (ev && ev.preventDefault) ev.preventDefault();
          lost++; restored = false;
          if (lost > 1) { fail(new Error('webgl context lost')); return; }
          setTimeout(function () {
            if (!restored && my === gen && !settled) fail(new Error('webgl context lost'));
          }, 800);
        });
        canvas.addEventListener('webglcontextrestored', function () { restored = true; });
      }
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
