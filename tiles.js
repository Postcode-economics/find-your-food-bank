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
window.TILE_VECTOR_WATCH_MS = 8000;
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
  /* No tiles (every provider failed, or this area was never cached): plain light background, markers untouched. */
  function paintPlain(on) {
    var el = document.getElementById('map');
    if (el) el.classList.toggle('notiles', !!on);
  }
  function plainIfEmpty() {
    if (!map.getContainer().querySelector('.leaflet-tile-loaded')) paintPlain(true);
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
          plainIfEmpty();
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
            paintPlain(false);
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
            paintPlain(false);
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
  function stopVectorWatch() {
    if (map._hmVectorWatch) { clearTimeout(map._hmVectorWatch); map._hmVectorWatch = 0; }
  }
  function useVector(p, my, i) {
    window.TILE_ACTIVE = p.name; logo(false);
    /* Fatal OpenFreeMap failures go back to OpenStreetMap (#200 on #201's map). vectorFailed allows that
       once per page: giveUp then never returns to OpenFreeMap. settled is set only in claim(). */
    var settled = false, sawLoad = false, sawIdle = false, sawPaint = false;
    function claim() {
      if (my !== gen || settled) return false;
      settled = true;
      stopVectorWatch();
      return true;
    }
    /* Style-document and source-load failures are fatal. A tile event, or a glyph, sprite or font miss, is not. */
    function fatalVectorError(ev) {
      var err = ev && ev.error;
      var msg, url, blob;
      if (!err) return false;
      msg = String(err.message || '');
      url = String(err.url || '');
      blob = (msg + ' ' + url).toLowerCase();
      if (/webgl/.test(blob)) return true;
      if (ev.tile) return false;
      if (/glyph|sprite|fontstack|\/fonts\//.test(blob)) return false;
      if (/\.pbf(?:\?|$)/.test(blob)) return false;
      if (ev.sourceId) return true;
      if (ev.layer) return false;
      if (ev.style) return true;
      return false;
    }
    function fail(e) {
      if (!claim()) return;
      if (layer) { try { map.removeLayer(layer); } catch (x) {} layer = null; }
      if (my !== gen) return;
      window.TILE_VECTOR = 'failed: ' + (e && e.message);
      if (i < list.length - 1) { use(i + 1); return; }
      if (!vectorFailed && list[0] && list[0].type !== 'vector') {
        vectorFailed = true;
        if (window.TILE_FAILOVER) window.TILE_FAILOVER.back = list[0].name;
        use(0);
      }
    }
    /* Opaque pixels, or features MapLibre can already query. A canvas with no style stays clear. */
    function painted(gl) {
      var cv, ctx, buf, lit, x, y, feats;
      try {
        if (gl.queryRenderedFeatures) {
          feats = gl.queryRenderedFeatures();
          if (feats && feats.length) return true;
        }
      } catch (e1) {}
      try {
        cv = gl.getCanvas();
        if (!cv || cv.width < 2 || cv.height < 2) return false;
        ctx = cv.getContext('webgl2') || cv.getContext('webgl');
        if (!ctx) return false;
        buf = new Uint8Array(4); lit = 0;
        for (y = 1; y <= 3; y++) for (x = 1; x <= 3; x++) {
          ctx.readPixels((cv.width * x / 4) | 0, (cv.height * y / 4) | 0, 1, 1, ctx.RGBA, ctx.UNSIGNED_BYTE, buf);
          if (buf[3] > 0) lit++;
        }
        return lit >= 3;
      } catch (e2) { return false; }
    }
    window.loadVectorLib().then(function () {
      if (my !== gen) return;
      /* Let a tap that arrived while the script was parsing run before WebGL setup. */
      return new Promise(function (ok) { setTimeout(ok, 0); });
    }).then(function () {
      if (my !== gen) return;
      if (!webglOk()) throw new Error('webgl unsupported');
      /* Light on phones (#170): no fades, a small tile cache, flat (no pitch or rotate).
         pixelRatio stays vectorPixelRatio (1 on a phone). trackResize stays false (#201). */
      layer = L.maplibreGL({ style: p.url, maxZoom: p.maxZoom || 19, pixelRatio: vectorPixelRatio(),
        trackResize: false, fadeDuration: 0, maxTileCacheSize: 32,
        antialias: false, maxPitch: 0, pitchWithRotate: false, dragRotate: false, touchPitch: false,
        refreshExpiredTiles: false, crossSourceCollisions: false,
        attributionControl: { customAttribution: p.attribution },
        /* Root-relative vector tiles never leave WebKit (0 requests, grey canvas, ready already set).
           Make them absolute before the worker fetches. */
        transformRequest: function (url) {
          /* WebKit asks for a root-relative vector tile on the page host and then drops it, so the
             canvas stays the grey background with ready already set and no tile counted. Send it to
             the tile host. */
          if (!url) return { url: url };
          if (url.charAt(0) === '/') url = 'https://tiles.openfreemap.org' + url;
          else if (url.indexOf('/planet/') >= 0 && url.indexOf('tiles.openfreemap.org') < 0)
            url = url.replace(/^https?:\/\/[^/]+/, 'https://tiles.openfreemap.org');
          return { url: url };
        } });
      layer.addTo(map);
      var glMap = layer.getMaplibreMap();
      var canvas = layer.getCanvas(), lost = 0, restored = true;
      if (!glMap) throw new Error('no map');
      window.TILE_VECTOR = 'loading';
      /* 'ready' only after MapLibre's load (PR 198). Setting it before load is the 27 Oct grey map:
         the canvas exists, WebKit has thrown, no vector tile is requested, and nothing falls back.
         kick() is what Locate / Find nearest need: those add this layer during fitBounds, and a zoom
         listener attached mid-animation misses the resize, so the canvas stays grey. */
      var kicked = false;
      function kick() {
        if (my !== gen || !glMap) return;
        try { glMap.resize(); } catch (eK) {}
        try { if (layer && layer._update) layer._update(); } catch (eU) {}
      }
      glMap.on('error', function (ev) {
        if (my !== gen) return;
        if (!kicked) { kicked = true; kick(); }
        if (settled || !fatalVectorError(ev)) return;
        fail(ev && ev.error || new Error('maplibre'));
      });
      glMap.on('load', function () {
        if (my !== gen) return;
        kick();
        consider(glMap, 'load');
      });
      glMap.on('idle', function () { consider(glMap, 'idle'); });
      /* Ready does not set settled. #201 still falls back if the WebGL context stays lost after paint.
         settled stays the gate on fail(), so that return happens once. */
      function succeed() {
        if (my !== gen || settled) return;
        stopVectorWatch();
        window.TILE_VECTOR = 'ready';
        paintPlain(false);
      }
      function consider(gl, kind) {
        if (my !== gen || settled) return;
        if (kind === 'load') sawLoad = true;
        if (kind === 'idle') sawIdle = true;
        try { if (painted(gl)) sawPaint = true; } catch (e3) {}
        /* Load is required. Idle alone must not mark the canvas ready before the style has loaded. */
        if (sawPaint && sawLoad) succeed();
      }
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
      stopVectorWatch();
      /* vector style timeout: a style that never loads, or a canvas that never paints, is the same miss. */
      map._hmVectorWatch = setTimeout(function () {
        map._hmVectorWatch = 0;
        if (my !== gen || settled) return;
        try { if (painted(glMap)) sawPaint = true; } catch (e4) {}
        if (sawPaint && sawLoad) succeed();
        else fail(new Error('no tiles'));
      }, window.TILE_VECTOR_WATCH_MS || 8000);
      map.on('moveend', kick);
      map.on('zoomend', kick);
      map.on('resize', kick);
      kick();
      setTimeout(kick, 400);
      setTimeout(kick, 1200);
    }).catch(fail);
  }
  map._hmTileStop = function () {
    gen++;
    stopVectorWatch();
    if (layer) { map.removeLayer(layer); layer = null; }
    if (logoCtl) { map.removeControl(logoCtl); logoCtl = null; }
  };
  use(0);
  if (/[?&]tiles=debug(&|$)/.test(location.search)) debugReadout(map);
  return layer;
};

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
