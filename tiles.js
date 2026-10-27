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
   The check keeps running after the first load. */
window.TILE_WINDOW = 20;
window.TILE_WINDOW_FAILS = 4;
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
  var list = window.tileCandidates(), gen = 0, layer = null, logoCtl = null;
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
    var n = i, switched = false, used = 0, ok = 0, bad = 0, recent = [];
    window.TILE_STATS = window.TILE_STATS || {load: 0, error: 0, probe: 0};
    function note(success) {
      if (success) ok++; else bad++;
      recent.push(success ? 1 : 0);
      var limit = window.TILE_WINDOW || 20;
      if (recent.length > limit) recent.shift();
      var windowBad = 0, k;
      for (k = 0; k < recent.length; k++) if (!recent[k]) windowBad++;
      return windowBad;
    }
    function giveUp(reason) {
      if (switched || my !== gen || n >= list.length - 1) return;
      switched = true;
      var windowBad = 0, k;
      for (k = 0; k < recent.length; k++) if (!recent[k]) windowBad++;
      window.TILE_FAILOVER = { from: p.name, to: list[n + 1].name, ok: ok, bad: bad, windowBad: windowBad, reason: String(reason) };
      use(n + 1);
    }
    var Layer = L.TileLayer.extend({
      createTile: function (coords, done) {
        var img = document.createElement('img'), size = this.getTileSize();
        img.alt = ''; img.width = size.x; img.height = size.y;
        if (p.cap && used >= p.cap) { done(null, img); return img; }
        if (p.cap) used++;
        var url = this.getTileUrl(coords), tileGen = my;
        window.TILE_STATS.probe++;
        fetch(url).then(function (r) {
          if (tileGen !== gen) return;
          if (r.status === 401 || r.status === 403 || r.status === 429) {
            window.TILE_STATS.error++;
            note(false);
            done(new Error(String(r.status)), img);
            giveUp(r.status);
            return;
          }
          if (!r.ok) {
            window.TILE_STATS.error++;
            var missed = note(false);
            done(new Error(String(r.status || 'tile')), img);
            if (missed >= (window.TILE_WINDOW_FAILS || 4)) giveUp('errors');
            return;
          }
          window.TILE_STATS.load++;
          if (note(true) >= (window.TILE_WINDOW_FAILS || 4)) giveUp('errors');
          /* The status is known now. The image uses the real tile URL, answered from the service worker
             or HTTP cache the fetch just filled, so img.src still names the provider (offline checks rely on it). */
          img.crossOrigin = 'anonymous';
          img.onload = function () { done(null, img); };
          img.onerror = function () {
            if (tileGen !== gen) return;
            window.TILE_STATS.error++;
            var failed = note(false);
            done(new Error('decode'), img);
            if (failed >= (window.TILE_WINDOW_FAILS || 4)) giveUp('errors');
          };
          img.src = url;
        }, function () {
          if (tileGen !== gen) return;
          window.TILE_STATS.error++;
          var failed = note(false);
          done(new Error('network'), img);
          if (failed >= (window.TILE_WINDOW_FAILS || 4)) giveUp('errors');
        });
        return img;
      }
    });
    layer = new Layer(providerUrl(p), { maxZoom: p.maxZoom || 19, attribution: p.attribution, crossOrigin: true });
    layer.addTo(map);
    window.TILE_ACTIVE = p.name;
    logo(p.name === 'maptiler');
  }
  /* OpenFreeMap: a MapLibre GL layer inside Leaflet. Markers, clusters and controls are unchanged. */
  function useVector(p, my, i) {
    window.TILE_ACTIVE = p.name; logo(false);
    window.loadVectorLib().then(function () {
      if (my !== gen) return;
      /* Light on phones: at most 2x pixels, no fades, a small tile cache, flat (no pitch or rotate). */
      layer = L.maplibreGL({ style: p.url, maxZoom: p.maxZoom || 19, attributionControl: { customAttribution: p.attribution },
        pixelRatio: Math.min(window.devicePixelRatio || 1, 2), fadeDuration: 0, maxTileCacheSize: 32,
        antialias: false, maxPitch: 0, pitchWithRotate: false, dragRotate: false, touchPitch: false,
        refreshExpiredTiles: false, crossSourceCollisions: false });
      layer.addTo(map);
      window.TILE_VECTOR = 'ready';
    }).catch(function (e) {
      if (my !== gen) return;
      window.TILE_VECTOR = 'failed: ' + (e && e.message);
      if (i < list.length - 1) use(i + 1);
    });
  }
  map._hmTileStop = function () {
    gen++;
    if (layer) { map.removeLayer(layer); layer = null; }
    if (logoCtl) { map.removeControl(logoCtl); logoCtl = null; }
  };
  use(0);
  return layer;
};
