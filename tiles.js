/* Map tiles, in the order they are tried.
   OpenStreetMap is the permanent default. Nothing in this file promotes another provider on a date,
   including 22 Nov, when a paused MapTiler quota may start working again.
   Stadia is the free backup and needs no key in this file. Its free plan is non-commercial.
   Localhost works with no key. A public site has to be registered on that plan (or paste a key
   into `key` below). helpmap.uk is not registered, so Stadia answers 401 until that is done.
   MapTiler is a paid fallback only. Paste a key into its `key` and it is tried last, with `cap`
   tile requests per page. A key does not make it the default.
   Reorder nothing to put MapTiler or Stadia first: tileCandidates() keeps OpenStreetMap first
   and MapTiler last even if this array is rearranged. */
window.TILE_PROVIDERS = [
  { name: 'osm', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>' },
  { name: 'stadia', key: '', url: 'https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}.png', maxZoom: 20,
    attribution: '&copy; <a href="https://stadiamaps.com/" target="_blank" rel="noopener">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>' },
  { name: 'maptiler', key: '', cap: 80, url: 'https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key={key}', maxZoom: 19,
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
    if (p.name === 'maptiler') return !!p.key;
    return !/\{key\}/.test(p.url) || !!p.key;
  });
  var osm = [], rest = [], paid = [];
  list.forEach(function (p) {
    if (p.name === 'osm') osm.push(p);
    else if (p.name === 'maptiler') paid.push(p);
    else rest.push(p);
  });
  return osm.concat(rest, paid);
};
window.addTiles = function (map) {
  if (map._hmTileStop) map._hmTileStop();
  var list = window.tileCandidates(), gen = 0, layer = null, logoCtl = null;
  window.TILE_ORDER = list.map(function (p) { return p.name; });
  function providerUrl(p) {
    var url = p.url;
    if (p.key && url.indexOf('{key}') >= 0) url = url.replace('{key}', encodeURIComponent(p.key));
    else if (p.key && p.name === 'stadia' && url.indexOf('api_key=') < 0)
      url += (url.indexOf('?') >= 0 ? '&' : '?') + 'api_key=' + encodeURIComponent(p.key);
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
          return r.blob().then(function (blob) {
            if (tileGen !== gen) return;
            var obj = URL.createObjectURL(blob);
            img.onload = function () { URL.revokeObjectURL(obj); done(null, img); };
            img.onerror = function () {
              URL.revokeObjectURL(obj);
              window.TILE_STATS.error++;
              var failed = note(false);
              done(new Error('decode'), img);
              if (failed >= (window.TILE_WINDOW_FAILS || 4)) giveUp('errors');
            };
            img.src = obj;
          });
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
  map._hmTileStop = function () {
    gen++;
    if (layer) { map.removeLayer(layer); layer = null; }
    if (logoCtl) { map.removeControl(logoCtl); logoCtl = null; }
  };
  use(0);
  return layer;
};
