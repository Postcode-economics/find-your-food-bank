/* Map tile providers, in order of preference (Dean, 22 Oct 2026: hardening against traffic spikes).
   The first provider with a key (or no key needed) is used; if its tiles keep failing the map switches to the next one.
   To add a keyed provider, paste the key into `key` below. Nothing else needs changing (CSP + service worker already allow these hosts). */
window.TILE_PROVIDERS = [
  { name: 'maptiler', key: 'xl3BtUpxQak69583G9Q6', url: 'https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key={key}', maxZoom: 19,
    attribution: '<a href="https://www.maptiler.com/copyright/" target="_blank" rel="noopener">&copy; MapTiler</a> <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">&copy; OpenStreetMap contributors</a>' },
  { name: 'stadia', key: '', url: 'https://tiles.stadiamaps.com/tiles/osm_bright/{z}/{x}/{y}.png?api_key={key}', maxZoom: 20,
    attribution: '&copy; <a href="https://stadiamaps.com/" target="_blank" rel="noopener">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>' },
  { name: 'osm', url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' }
];
/* addTiles(map): adds the first usable provider, and moves down the list when >=6 of the last ~20 tile loads fail. */
window.addTiles = function (map) {
  var list = window.TILE_PROVIDERS.filter(function (p) { return !/\{key\}/.test(p.url) || p.key; }), n = 0, layer = null;
  function use(i) {
    var p = list[i]; if (!p) return; n = i; var ok = 0, bad = 0;
    if (layer) map.removeLayer(layer);
    layer = L.tileLayer(p.url.replace('{key}', encodeURIComponent(p.key || '')), { maxZoom: p.maxZoom || 19, attribution: p.attribution, crossOrigin: true });
    layer.on('tileload', function () { if (++ok > 40) { ok = 20; bad = 0; } });
    layer.on('tileerror', function () { if (++bad >= 6 && bad * 3 > ok && n < list.length - 1) use(n + 1); });
    layer.addTo(map); window.TILE_ACTIVE = p.name; logo(p.name === 'maptiler');
  }
  /* MapTiler free plan: visible logo linking to maptiler.com while MapTiler tiles are shown. */
  var logoCtl = null;
  function logo(on) {
    if (on && !logoCtl) {
      logoCtl = L.control({ position: 'bottomleft' });
      logoCtl.onAdd = function () { var a = L.DomUtil.create('a', 'maptiler-logo'); a.href = 'https://www.maptiler.com/'; a.target = '_blank'; a.rel = 'noopener';
        a.setAttribute('aria-label', 'MapTiler'); a.innerHTML = '<img src="vendor/maptiler-logo.svg" alt="MapTiler logo" width="80" height="24" style="display:block">'; return a; };
      logoCtl.addTo(map);
    } else if (!on && logoCtl) { map.removeControl(logoCtl); logoCtl = null; }
  }
  use(0); return layer;
};
