"""Local checks only. Nothing here opens https://helpmap.uk or a map-tile host.

    python3 scripts/offline_env.py pytest
    python3 scripts/offline_env.py journeys
    python3 scripts/offline_env.py design-lock
    python3 scripts/offline_env.py old-links

pytest, journeys, design lock and old links then run against this checkout.
A remote URL is refused. stub() answers tile hosts with a local PNG so a
check never pans OpenStreetMap, OpenFreeMap, MapTiler or Stadia.
HELPMAP_REAL_TILES=1 leaves that route off. This file does not block DNS:
scripts/check_browser.py sends tiles to the CI tileserver when
HELPMAP_OFFLINE_TILES is set, and a DNS failure would stop that route
from ever seeing the request.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
# 1x1 PNG. Leaflet only needs a 200 image response.
PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
    b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)
# Whole host, not only a .png path: a style or tile URL on these hosts is still a pan.
TILE_RE = re.compile(
    r'https://(?:(?:[a-z0-9-]+\.)*tile\.openstreetmap\.org|api\.maptiler\.com|'
    r'tiles\.stadiamaps\.com|tiles\.openfreemap\.org)/',
    re.I)
_REMOTE = re.compile(r'https?://|helpmap\.uk', re.I)
COMMANDS = {
    'pytest': [sys.executable, '-m', 'pytest', '-q', 'tests'],
    'journeys': [sys.executable, os.path.join('scripts', 'journeys.py')],
    'design-lock': [sys.executable, os.path.join('scripts', 'design_lock.py')],
    'old-links': [sys.executable, os.path.join('scripts', 'old_links.py')],
}


def is_tile(url):
    return bool(TILE_RE.search(url or ''))


def install():
    """Kept so older callers do not crash. DNS blocking is not installed.

    HELPMAP_OFFLINE_TILES routes tile hosts to a local tileserver. A
    host-resolver rule that maps those hosts to ~NOTFOUND stops the
    request before that route can answer it.
    """
    return False


def stub(target):
    """Fulfill tile-host requests locally, status 200. No network.

    Call this again after unroute(), and after any catch-all route(): the later
    route is the one Playwright uses, and unroute of a catch-all can drop this one.
    """
    if os.environ.get('HELPMAP_REAL_TILES') == '1':
        return False

    def _stub(route):
        route.fulfill(status=200, content_type='image/png', body=PNG, headers={
            'access-control-allow-origin': '*',
            'cache-control': 'public, max-age=604800',
            'x-helpmap-tile': 'stub',
        })

    target.route(TILE_RE, _stub)
    return True


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    names = list(COMMANDS)
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print('usage: python3 scripts/offline_env.py %s' % '|'.join(names), file=sys.stderr)
        return 2
    if _REMOTE.search(' '.join(argv[1:])):
        print('offline_env refuses a remote URL', file=sys.stderr)
        return 2
    if argv[2:]:
        print('offline_env takes the check name only', file=sys.stderr)
        return 2
    os.environ['HELPMAP_OFFLINE'] = '1'
    os.chdir(ROOT)
    cmd = COMMANDS[argv[1]]
    print('offline_env: %s' % ' '.join(cmd), flush=True)
    return subprocess.call(cmd)


if __name__ == '__main__':
    sys.exit(main())
