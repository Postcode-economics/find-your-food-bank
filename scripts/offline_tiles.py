"""Opt-in offline map tiles for the browser checks (rules 23 and 26).

By default nothing changes: checks behave exactly as before. When HELPMAP_OFFLINE_TILES is set to the
base URL of a local tile server (for example http://127.0.0.1:8089, the UK OpenStreetMap server on the
bot box: /workspace/offline_map/start.sh), every map tile request the site makes to
tile.openstreetmap.org, MapTiler or Stadia is answered from that local server instead, so the map
shows real streets and no request ever reaches a public tile host.

The local server must serve 256px raster tiles at  <base>/styles/<style>/256/{z}/{x}/{y}.png
(tileserver-gl's layout). HELPMAP_OFFLINE_TILES_STYLE picks the style (default: bright).
"""
import os
import re
import urllib.request

ENV = 'HELPMAP_OFFLINE_TILES'
EXTERNAL_TILE_HOSTS = ('tile.openstreetmap.org', 'api.maptiler.com', 'tiles.stadiamaps.com',
                       'tiles.openfreemap.org', 'basemaps.cartocdn.com', 'server.arcgisonline.com')
_ZXY = re.compile(r'/(\d+)/(\d+)/(\d+)(?:@2x)?\.(?:png|jpg|jpeg|webp)$')
_HOST_RE = re.compile(r'^https?://([a-z0-9-]+\.)*(' + '|'.join(re.escape(h) for h in EXTERNAL_TILE_HOSTS) + r')(:\d+)?/')


def base_url(env=None):
    v = ((env if env is not None else os.environ).get(ENV) or '').strip().rstrip('/')
    return v or None


def is_external_tile_host(url):
    return bool(_HOST_RE.match(url or ''))


def local_tile_url(url, base, style=None):
    """The local equivalent of an external tile URL, or None if it is not a z/x/y tile."""
    m = _ZXY.search((url or '').split('?', 1)[0].split('#', 1)[0])
    if not m:
        return None
    style = style or os.environ.get(ENV + '_STYLE') or 'bright'
    return '%s/styles/%s/256/%s/%s/%s.png' % (base, style, m.group(1), m.group(2), m.group(3))


class Stats:
    def __init__(self):
        self.served = 0
        self.failed = 0
        self.external = []   # external tile requests that were NOT answered locally (should stay empty)


def attach(context, base=None, fetch=None):
    """Route external tile hosts on a Playwright context to the local server. Returns Stats.
    Anything on a tile host that is not a z/x/y tile is aborted, never sent out."""
    base = base or base_url()
    stats = Stats()
    if not base:
        return stats
    fetch = fetch or (lambda u: urllib.request.urlopen(u, timeout=20).read())

    def handle(route):
        url = route.request.url
        local = local_tile_url(url, base)
        if not local:
            stats.external.append(url)
            return route.abort()
        try:
            body = fetch(local)
        except Exception:
            stats.failed += 1
            return route.fulfill(status=404, body=b'')
        stats.served += 1
        route.fulfill(status=200, body=body, headers={'content-type': 'image/png',
                                                      'access-control-allow-origin': '*',
                                                      'cache-control': 'no-store'})

    context.route(_HOST_RE, handle)
    context.offline_tile_stats = stats
    return stats
