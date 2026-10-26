"""Ask each map provider for one tile and flag any response that is not HTTP 200.

One tile, not a pan. OpenStreetMap's tile policy forbids headless browsers panning the map;
this job is a single identified request per provider. Run daily from .github/workflows/tile-monitor.yml.

MapTiler is skipped while its `key` in tiles.js is blank, because that URL cannot succeed and
it is only a paid fallback. A skipped provider is not a failure. A real non-200 is.
"""
import os, re, sys, urllib.error, urllib.parse, urllib.request

ROOT = os.path.join(os.path.dirname(__file__), '..')
UA = 'helpmap.uk-tile-monitor/1.0 (+https://helpmap.uk; hello@helpmap.uk)'
REFERER = 'https://helpmap.uk/'
# One overview tile covering northern England. Not a sweep.
Z, X, Y = 6, 31, 20


def providers(text=None):
    text = text if text is not None else open(os.path.join(ROOT, 'tiles.js'), encoding='utf-8').read()
    body = text.split('window.TILE_PROVIDERS', 1)[1].split('];', 1)[0]
    out = []
    for chunk in re.split(r'\},\s*', body):
        if "name:" not in chunk:
            continue

        def field(name, default='', chunk=chunk):
            m = re.search(r"\b%s\s*:\s*'([^']*)'" % name, chunk)
            if m:
                return m.group(1)
            m = re.search(r'\b%s\s*:\s*(\d+)' % name, chunk)
            if m:
                return int(m.group(1))
            return default

        out.append({'name': field('name'), 'url': field('url'), 'key': field('key', ''), 'cap': field('cap', 0) or 0})
    return out


def request_url(p, z=Z, x=X, y=Y):
    """A single tile URL, or None when the provider has no key to put in a {key} URL."""
    url = p.get('url') or ''
    key = p.get('key') or ''
    if '{key}' in url:
        if not key:
            return None
        url = url.replace('{key}', urllib.parse.quote(key, safe=''))
    elif key and p.get('name') == 'stadia' and 'api_key=' not in url:
        url += ('&' if '?' in url else '?') + 'api_key=' + urllib.parse.quote(key, safe='')
    return url.replace('{z}', str(z)).replace('{x}', str(x)).replace('{y}', str(y)).replace('{s}', 'a')


def check_one(p, open_url=None):
    url = request_url(p)
    if not url:
        return {'name': p.get('name'), 'url': '', 'status': 'skipped', 'flag': False, 'detail': 'no key'}
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': REFERER}, method='GET')
    open_url = open_url or urllib.request.urlopen
    try:
        with open_url(req, timeout=20) as r:
            status = getattr(r, 'status', None) or r.getcode()
            r.read(64)
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        return {'name': p.get('name'), 'url': url, 'status': 0, 'flag': True, 'detail': str(e).splitlines()[0][:180]}
    return {'name': p.get('name'), 'url': url, 'status': status, 'flag': status != 200, 'detail': ''}


def run(open_url=None):
    return [check_one(p, open_url=open_url) for p in providers()]


def main():
    rows = run()
    bad = []
    for row in rows:
        line = '%s %s' % (row['name'], row['status'])
        if row['detail']:
            line += ' (%s)' % row['detail']
        if row['flag']:
            line += ' FLAGGED'
            bad.append(line)
        print(line)
    if bad:
        print('tile monitor: %d provider(s) did not return 200' % len(bad))
        return 1
    print('tile monitor: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
