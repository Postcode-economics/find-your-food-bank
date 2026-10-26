"""Local-only server and Playwright context for helpmap.uk tests.

The server is the same kind of static server as ``python -m http.server``. ``data.js`` and the
stamp files are copied once, at start, and those copies are what the browser receives. Tile hosts
are answered with a blank PNG. ``helpmap.uk`` is answered from this checkout. Any other host is
logged and rejected, and the run fails.
"""
import argparse
import datetime
import hashlib
import http.client
import http.server
import json
import mimetypes
import os
import posixpath
import shutil
import signal
import struct
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
HELP_MAP_ORIGIN = 'https://helpmap.uk'
# Root files frozen for the life of one harness process. Anything else is read from the checkout,
# so an agent's HTML/JS edits show up immediately and a refresh of data.js does not.
SNAPSHOT_FILES = ('data.js', 'data.full.js', 'stamp.js')
TILE_HOSTS = (
    'tile.openstreetmap.org',
    '*.tile.openstreetmap.org',
    'openfreemap.org',
    '*.openfreemap.org',
    'api.maptiler.com',
    'stadiamaps.com',
    '*.stadiamaps.com',
)
_IGNORE_SCHEMES = frozenset((
    '', 'about', 'blob', 'data', 'chrome', 'chrome-error', 'chrome-extension', 'devtools',
))
_LAUNCH_ARGS = (
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-default-apps',
    '--disable-domain-reliability',
    '--disable-sync',
    '--metrics-recording-only',
    '--no-default-browser-check',
    '--no-first-run',
    '--disable-dev-shm-usage',
    '--disable-features=OptimizationHints,MediaRouter',
)
_EXTRA_MIME = {
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.html': 'text/html; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.webmanifest': 'application/manifest+json',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
    '.woff2': 'font/woff2',
}

_ACTIVE = None  # in-process server started by start()


class ExternalRequest(AssertionError):
    """A browser request left the allowed set (loopback, helpmap.uk files, tile stubs)."""


def _png_chunk(tag, data):
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)


def blank_png():
    """1x1 transparent PNG. Leaflet treats a decoded image as a successful tile, so it does not
    walk the provider list or open another connection."""
    raw = b'\x00\x00\x00\x00\x00'  # filter byte + RGBA pixel
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + _png_chunk(b'IHDR', ihdr) + _png_chunk(b'IDAT', zlib.compress(raw)) + _png_chunk(b'IEND', b'')


BLANK_PNG = blank_png()


def _host(url):
    name = urllib.parse.urlsplit(url).hostname or ''
    return name.lower().rstrip('.')


def _matches(host, pattern):
    if pattern.startswith('*.'):
        rest = pattern[2:]
        return host == rest or host.endswith('.' + rest)
    return host == pattern


def is_tile_host(host):
    host = (host or '').lower().split(':')[0].rstrip('.')
    return any(_matches(host, pattern) for pattern in TILE_HOSTS)


def is_helpmap(host):
    host = (host or '').lower().split(':')[0].rstrip('.')
    return host == 'helpmap.uk' or host.endswith('.helpmap.uk')


def is_loopback(host):
    host = (host or '').lower().split(':')[0].rstrip('.')
    return host in ('127.0.0.1', 'localhost', '::1', '[::1]')


def classify(url):
    """``tile``, ``helpmap``, ``loopback``, ``ignore``, or ``external``."""
    parts = urllib.parse.urlsplit(url or '')
    scheme = (parts.scheme or '').lower()
    if scheme in _IGNORE_SCHEMES:
        return 'ignore'
    if scheme not in ('http', 'https', 'ws', 'wss'):
        return 'external'
    host = (parts.hostname or '').lower().rstrip('.')
    if is_tile_host(host):
        return 'tile'
    if is_helpmap(host):
        return 'helpmap'
    if is_loopback(host):
        return 'loopback'
    return 'external'


def content_type(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in _EXTRA_MIME:
        return _EXTRA_MIME[ext]
    return mimetypes.guess_type(path)[0] or 'application/octet-stream'


def snapshot_names(root):
    names = set()
    for name in SNAPSHOT_FILES:
        if os.path.isfile(os.path.join(root, name)):
            names.add(name)
    try:
        for name in os.listdir(root):
            path = os.path.join(root, name)
            if os.path.isfile(path) and 'stamp' in name.lower():
                names.add(name)
    except OSError:
        pass
    missing = [name for name in ('data.js', 'stamp.js') if name not in names]
    if missing:
        raise SystemExit('offline harness: missing %s in %s' % (', '.join(missing), root))
    return names


def snapshot(root=None, dest=None):
    """Copy ``data.js`` and the stamp files. Returns the snapshot directory."""
    root = os.path.abspath(root or os.environ.get('OFFLINE_ROOT') or REPO)
    names = snapshot_names(root)
    if dest is None:
        dest = tempfile.mkdtemp(prefix='offline-env-')
        owned = True
    else:
        os.makedirs(dest, exist_ok=True)
        owned = False
    manifest = {'root': root, 'created': _now(), 'files': {}}
    for name in sorted(names):
        src = os.path.join(root, name)
        dst = os.path.join(dest, name)
        shutil.copyfile(src, dst)
        data = open(dst, 'rb').read()
        manifest['files'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    manifest['owned'] = owned
    json.dump(manifest, open(os.path.join(dest, 'MANIFEST.json'), 'w'), indent=1)
    return dest


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _inside(path, root):
    path = os.path.realpath(path)
    root = os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def local_path(root, snapshot_dir, names, url_path):
    """Map a URL path onto the snapshot (data.js, stamps) or a file in the checkout.

    Returns ``(filesystem path or None, tag)`` where tag is ``snapshot``, ``repo``, or ``missing``.
    """
    raw = urllib.parse.unquote(urllib.parse.urlsplit(url_path).path or '/')
    rel = posixpath.normpath(raw)
    if rel.startswith('../') or rel == '..' or rel.startswith('/..'):
        return None, 'missing'
    rel = rel.lstrip('/')
    if rel in ('', '.'):
        rel = 'index.html'
    parts = [p for p in rel.split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts):
        return None, 'missing'
    if len(parts) == 1 and parts[0] in names:
        cand = os.path.join(snapshot_dir, parts[0])
        if os.path.isfile(cand) and _inside(cand, snapshot_dir):
            return cand, 'snapshot'
        return None, 'missing'
    cand = os.path.join(root, *parts) if parts else root
    if not _inside(cand, root):
        return None, 'missing'
    if os.path.isdir(cand):
        cand = os.path.join(cand, 'index.html')
    if os.path.isfile(cand):
        return cand, 'repo'
    return None, 'missing'


class RequestLog:
    """Append-only JSONL log. ``external`` rows fail the run."""

    def __init__(self, path=None):
        self.path = path
        self.events = []
        self._lock = threading.Lock()

    def add(self, kind, method, url, **extra):
        rec = {'ts': _now(), 'kind': kind, 'method': method or 'GET', 'url': url}
        rec.update(extra)
        line = (json.dumps(rec, separators=(',', ':')) + '\n').encode()
        with self._lock:
            self.events.append(rec)
            if self.path:
                fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
                try:
                    os.write(fd, line)
                finally:
                    os.close(fd)
        if kind == 'external':
            note = 'leaked' if extra.get('leaked') else 'blocked'
            print('OFFLINE external %s: %s %s' % (note, rec['method'], url), file=sys.stderr, flush=True)
        return rec

    def of(self, kind):
        return [e for e in self.events if e['kind'] == kind]

    def external_urls(self):
        return [e['url'] for e in self.of('external')]

    def assert_clean(self):
        urls = self.external_urls()
        if urls:
            shown = '\n'.join('  %s' % u for u in urls[:30])
            more = '' if len(urls) <= 30 else '\n  … %d more' % (len(urls) - 30)
            raise ExternalRequest('external request(s) during offline run (%d):\n%s%s' % (len(urls), shown, more))

    def forget(self, url):
        """Drop a deliberate probe (the self-check) from memory and from the log file."""
        with self._lock:
            self.events = [e for e in self.events if e['url'] != url]
            if not self.path or not os.path.exists(self.path):
                return
            kept = []
            for line in open(self.path, encoding='utf-8'):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    kept.append(line if line.endswith('\n') else line + '\n')
                    continue
                if rec.get('url') == url and rec.get('kind') == 'external':
                    continue
                kept.append(line if line.endswith('\n') else line + '\n')
            tmp = self.path + '.tmp'
            open(tmp, 'w', encoding='utf-8').write(''.join(kept))
            os.replace(tmp, self.path)


def assert_log_clean(path):
    """Exit status for ``run.sh``: 0 when the JSONL log has no external rows."""
    bad = []
    if path and os.path.exists(path):
        for line in open(path, encoding='utf-8'):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get('kind') == 'external':
                bad.append('%s %s' % (rec.get('method') or 'GET', rec.get('url') or ''))
    if bad:
        print('offline harness: %d external request(s)' % len(bad), file=sys.stderr)
        for row in bad[:50]:
            print('  ' + row, file=sys.stderr)
        if len(bad) > 50:
            print('  … %d more' % (len(bad) - 50), file=sys.stderr)
        return 1
    return 0


def _append_server(log_path, method, path, code):
    if not log_path:
        return
    rec = {'ts': _now(), 'kind': 'server', 'method': method, 'url': path, 'status': code}
    line = (json.dumps(rec, separators=(',', ':')) + '\n').encode()
    fd = os.open(log_path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def make_handler(root, snapshot_dir, names, log_path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root, **kwargs)

        def _forbid_proxy(self):
            target = urllib.parse.unquote(self.path or '')
            if target.startswith(('http://', 'https://', '//')) or '://' in target.split('?', 1)[0]:
                self.send_error(403, 'offline harness does not proxy')
                return True
            return False

        def _safe(self, method):
            if self._forbid_proxy():
                return
            try:
                method()
            except (BrokenPipeError, ConnectionResetError):
                # The client closed while a large file (data.js) was still going out.
                pass

        def do_GET(self):
            self._safe(super().do_GET)

        def do_HEAD(self):
            self._safe(super().do_HEAD)

        def do_POST(self):
            self.send_error(403, 'offline harness does not accept posts')

        def do_CONNECT(self):
            self.send_error(403, 'offline harness does not proxy')

        def translate_path(self, path):
            local, tag = local_path(root, snapshot_dir, names, path)
            self._offline_tag = tag
            if local:
                return local
            # A path that does not resolve. send_head then returns 404 without listing the disk.
            return os.path.join(root, '__offline_missing__')

        def end_headers(self):
            self.send_header('X-Offline-Env', getattr(self, '_offline_tag', 'repo'))
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

        def guess_type(self, path):
            return content_type(path)

        def log_message(self, fmt, *args):
            code = args[1] if len(args) > 1 else ''
            _append_server(log_path, self.command, self.path, str(code))
            if str(code).startswith(('4', '5')):
                sys.stderr.write('offline-env %s %s\n' % (self.path, fmt % args))

    return Handler


class BoundServer:
    def __init__(self, httpd, thread):
        self.httpd = httpd
        self.thread = thread
        self.base = 'http://127.0.0.1:%d/' % httpd.server_address[1]

    def stop(self):
        if self.httpd is None:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.httpd = None


def serve(root=None, host='127.0.0.1', port=0, snapshot_dir=None, log_path=None, background=True):
    """Listen on loopback and serve the checkout, with the snapshot standing in for data.js and stamps."""
    root = os.path.abspath(root or os.environ.get('OFFLINE_ROOT') or REPO)
    if snapshot_dir is None:
        snapshot_dir = snapshot(root)
    names = snapshot_names(root)
    handler = make_handler(root, snapshot_dir, names, log_path)
    httpd = http.server.ThreadingHTTPServer((host, int(port)), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, name='offline-env', daemon=True)
    thread.start()
    bound = BoundServer(httpd, thread)
    _wait_ready(bound.base)
    if background:
        return bound, snapshot_dir
    return httpd, snapshot_dir


class Offline:
    """One running harness: snapshot, loopback server, and the request log."""

    def __init__(self, root, snapshot_dir, server, log_path, owns=True):
        self.root = root
        self.snapshot = snapshot_dir
        self.server = server
        self.log_path = log_path
        self.owns = owns
        self.base = server.base if server is not None else os.environ.get('OFFLINE_BASE', '')
        self.helpmap = HELP_MAP_ORIGIN
        self.log = RequestLog(log_path)
        manifest = os.path.join(snapshot_dir, 'MANIFEST.json')
        self.manifest = json.load(open(manifest)) if os.path.isfile(manifest) else {'files': {}}

    @classmethod
    def attach(cls, base, snapshot_dir, log_path, root):
        env = cls(root or REPO, snapshot_dir, server=None, log_path=log_path, owns=False)
        env.base = base if base.endswith('/') else base + '/'
        return env

    def assert_clean(self):
        """Fail when this process logged an external request. Also re-reads the shared log file."""
        self.log.assert_clean()
        if self.log_path and assert_log_clean(self.log_path) != 0:
            raise ExternalRequest('external request(s) in %s' % self.log_path)

    def close(self):
        global _ACTIVE
        if not self.owns:
            return
        if self.server is not None:
            self.server.stop()
            self.server = None
        if self.snapshot and os.path.isdir(self.snapshot) and self.manifest.get('owned', True):
            shutil.rmtree(self.snapshot, ignore_errors=True)
        if _ACTIVE is self:
            _ACTIVE = None


def _ping(base):
    url = base.rstrip('/') + '/stamp.js'
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200 and resp.headers.get('X-Offline-Env') == 'snapshot'
    except Exception:
        return False


def _wait_ready(base, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _ping(base):
            return
        time.sleep(0.02)
    raise SystemExit('offline harness: server did not answer on %s' % base)


def current():
    """The in-process server, or the one ``run.sh`` put in the environment."""
    if _ACTIVE is not None and _ACTIVE.server is not None:
        return _ACTIVE
    base = os.environ.get('OFFLINE_BASE')
    snap = os.environ.get('OFFLINE_SNAPSHOT')
    if base and snap and os.path.isdir(snap) and _ping(base):
        return Offline.attach(base, snap, os.environ.get('OFFLINE_LOG'), os.environ.get('OFFLINE_ROOT') or REPO)
    return None


def start(root=None, port=0, host='127.0.0.1', log_path=None):
    """Start the offline server, or attach to the one already started by ``run.sh``."""
    global _ACTIVE
    env = current()
    if env is not None:
        return env
    root = os.path.abspath(root or os.environ.get('OFFLINE_ROOT') or REPO)
    snap = snapshot(root)
    if log_path is None:
        log_path = os.environ.get('OFFLINE_LOG') or os.path.join(snap, 'requests.jsonl')
    server, snap = serve(root, host=host, port=port, snapshot_dir=snap, log_path=log_path, background=True)
    env = Offline(root, snap, server, log_path, owns=True)
    _ACTIVE = env
    return env


def _check_browser():
    import importlib
    try:
        return importlib.import_module('check_browser')
    except ImportError:
        scripts = os.path.join(REPO, 'scripts')
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        return importlib.import_module('check_browser')


def _fulfill_file(route, path, tag):
    body = open(path, 'rb').read()
    route.fulfill(status=200, body=body, headers={
        'content-type': content_type(path),
        'cache-control': 'no-store',
        'x-offline-env': tag,
    })


def dispatch(route, env, log):
    """Playwright route body. Never calls ``route.fetch`` and never continues an external URL."""
    request = route.request
    url = request.url
    kind = classify(url)
    method = request.method
    if kind == 'ignore':
        route.continue_()
        return
    if kind == 'tile':
        log.add('tile', method, url)
        route.fulfill(status=200, body=BLANK_PNG, headers={
            'content-type': 'image/png',
            'cache-control': 'no-store',
            'access-control-allow-origin': '*',
            'x-offline-env': 'tile',
        })
        return
    if kind in ('helpmap', 'loopback'):
        path, tag = local_path(env.root, env.snapshot, set(env.manifest.get('files') or snapshot_names(env.root)), url)
        # Loopback pages are the harness server, which already applies the snapshot. Intercept the
        # frozen files here as well so a plain static server cannot serve a newer data.js.
        if kind == 'loopback' and tag != 'snapshot':
            log.add('local', method, url)
            route.continue_()
            return
        if path:
            log.add('local', method, url, source=tag)
            _fulfill_file(route, path, tag)
            return
        log.add('local', method, url, source='missing')
        route.fulfill(status=404, body=b'', headers={
            'content-type': 'text/plain; charset=utf-8',
            'x-offline-env': 'missing',
            'cache-control': 'no-store',
        })
        return
    log.add('external', method, url)
    route.abort('blockedbyclient')


class Routed:
    """A Playwright context whose traffic stays inside the harness."""

    def __init__(self, context, log, env, owns_env):
        self.context = context
        self.log = log
        self.env = env
        self.owns_env = owns_env
        self.base = env.base
        self.helpmap = env.helpmap

    def new_page(self):
        return self.context.new_page()

    def assert_clean(self):
        self.log.assert_clean()

    def close(self, check=True):
        try:
            self.context.close()
            if check:
                self.log.assert_clean()
        finally:
            if self.owns_env:
                self.env.close()


def install(context, env, log):
    # Playwright calls the handler with (route, request) and then keeps only as many arguments
    # as the callable declares. A second parameter would be bound to the request, so env and log
    # stay in the closure and this function takes the route alone.
    def handle(route):
        dispatch(route, env, log)
    context.route('**/*', handle)
    return log


def offline_context(browser, offline=None, **kwargs):
    """Context factory other tests import.

    ``browser`` is a Playwright browser. Keyword arguments are passed to the shared
    ``check_browser.new_context`` (viewport, color_scheme, geolocation, …). Service workers
    stay blocked unless the caller sets ``service_workers``. The returned :class:`Routed`
    has ``new_page``, ``base`` (loopback), ``helpmap`` (``https://helpmap.uk``, served from
    disk), ``assert_clean``, and ``close``.
    """
    owns = False
    env = offline
    if env is None:
        env = current()
    if env is None:
        env = start()
        owns = True
    helper = _check_browser()
    kwargs.setdefault('service_workers', 'block')
    context = helper.new_context(browser, **kwargs)
    log = RequestLog(env.log_path)
    install(context, env, log)
    return Routed(context, log, env, owns_env=owns and offline is None)


def launch(playwright, **kwargs):
    """Chromium with background updates and telemetry switches off.

    Uses ``executable_path`` when the caller passes one or ``OFFLINE_CHROME`` is set. Otherwise
    tries Playwright's Chromium, then ``/usr/bin/google-chrome``. Adds ``--no-sandbox`` when
    running as root, in a container, or when ``OFFLINE_NO_SANDBOX=1``.
    """
    args = list(kwargs.pop('args', []))
    for arg in _LAUNCH_ARGS:
        if arg not in args:
            args.append(arg)
    if os.geteuid() == 0 or os.environ.get('OFFLINE_NO_SANDBOX') == '1' or os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv'):
        if '--no-sandbox' not in args:
            args.append('--no-sandbox')
    kwargs['args'] = args
    exe = kwargs.get('executable_path') or os.environ.get('OFFLINE_CHROME')
    if exe:
        kwargs['executable_path'] = exe
        return playwright.chromium.launch(**kwargs)
    try:
        return playwright.chromium.launch(**kwargs)
    except Exception as first:
        chrome = '/usr/bin/google-chrome' if os.path.exists('/usr/bin/google-chrome') else None
        if not chrome:
            raise
        kwargs['executable_path'] = chrome
        if '--no-sandbox' not in kwargs['args']:
            kwargs['args'].append('--no-sandbox')
        try:
            return playwright.chromium.launch(**kwargs)
        except Exception:
            raise first


def _serve_cli(args):
    root = os.path.abspath(args.root or REPO)
    snap = snapshot(root)
    log_path = args.log or os.path.join(snap, 'requests.jsonl')
    httpd, snap = serve(root, host=args.host, port=args.port, snapshot_dir=snap, log_path=log_path, background=False)
    base = 'http://127.0.0.1:%d/' % httpd.server_address[1]
    state = {
        'base': base,
        'snapshot': snap,
        'log': log_path,
        'root': root,
        'pid': os.getpid(),
    }
    if args.state:
        tmp = args.state + '.tmp'
        json.dump(state, open(tmp, 'w'))
        os.replace(tmp, args.state)
    print('OFFLINE_BASE=%s' % base, file=sys.stderr, flush=True)
    print('OFFLINE_SNAPSHOT=%s' % snap, file=sys.stderr, flush=True)
    stop_flag = threading.Event()

    def stop(signum, frame):
        stop_flag.set()
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        stop_flag.wait()
    finally:
        try:
            httpd.shutdown()
        except Exception:
            pass
        httpd.server_close()
        shutil.rmtree(snap, ignore_errors=True)


def _self_check(use_browser):
    failures = []

    def check(cond, why):
        if cond:
            print('ok', why)
        else:
            failures.append(why)
            print('FAIL', why)

    png = BLANK_PNG
    check(png.startswith(b'\x89PNG\r\n\x1a\n') and png.endswith(b'IEND\xaeB`\x82'), 'blank png')
    check(is_tile_host('tile.openstreetmap.org'), 'osm host')
    check(is_tile_host('a.tile.openstreetmap.org'), 'osm subdomain')
    check(is_tile_host('tiles.openfreemap.org'), 'openfreemap')
    check(is_tile_host('api.maptiler.com'), 'maptiler')
    check(is_tile_host('tiles.stadiamaps.com'), 'stadia tiles')
    check(not is_tile_host('www.openstreetmap.org'), 'osm website is not a tile host')
    check(not is_tile_host('www.maptiler.com'), 'maptiler website is not a tile host')
    check(is_helpmap('helpmap.uk') and is_helpmap('www.helpmap.uk'), 'helpmap hosts')
    check(not is_helpmap('helpmap.uk.example.com'), 'lookalike host is external')
    samples = {
        'https://tile.openstreetmap.org/6/31/20.png': 'tile',
        'https://a.tile.openstreetmap.org/1/0/0.png': 'tile',
        'https://tiles.openfreemap.org/planet/0/0/0.pbf': 'tile',
        'https://api.maptiler.com/maps/streets-v2/256/6/31/20.png?key=': 'tile',
        'https://tiles.stadiamaps.com/tiles/osm_bright/1/0/0.png': 'tile',
        'https://helpmap.uk/data.js?v=1': 'helpmap',
        'https://www.helpmap.uk/': 'helpmap',
        'http://127.0.0.1:9/index.html': 'loopback',
        'https://api.postcodes.io/postcodes/BN175LF': 'external',
        'https://static.cloudflareinsights.com/beacon.min.js': 'external',
        'https://formsubmit.co/ajax/x': 'external',
        'https://example.com/': 'external',
        'data:image/png;base64,xx': 'ignore',
    }
    check(all(classify(url) == kind for url, kind in samples.items()), 'classify hosts')

    env = start()
    try:
        import urllib.request
        with urllib.request.urlopen(env.base + 'data.js', timeout=5) as resp:
            body = resp.read()
            tag = resp.headers.get('X-Offline-Env')
        snap_body = open(os.path.join(env.snapshot, 'data.js'), 'rb').read()
        check(tag == 'snapshot' and body == snap_body, 'GET /data.js is the snapshot')
        # Prove the server is not reading the checkout copy: change only the snapshot.
        with open(os.path.join(env.snapshot, 'data.js'), 'ab') as fh:
            fh.write(b'\n/*offline-env-probe*/\n')
        with urllib.request.urlopen(env.base + 'data.js', timeout=5) as resp:
            changed = resp.read()
        repo_body = open(os.path.join(env.root, 'data.js'), 'rb').read()
        check(changed != repo_body and changed.endswith(b'/*offline-env-probe*/\n'), 'data.js stays on the snapshot after the checkout copy would differ')
        with urllib.request.urlopen(env.base + 'stamp.js', timeout=5) as resp:
            stamp = resp.read()
            stamp_tag = resp.headers.get('X-Offline-Env')
        check(stamp_tag == 'snapshot' and stamp == open(os.path.join(env.snapshot, 'stamp.js'), 'rb').read(), 'GET /stamp.js is the snapshot')
        with urllib.request.urlopen(env.base + 'index.html', timeout=5) as resp:
            page = resp.read()
            page_tag = resp.headers.get('X-Offline-Env')
        check(page_tag == 'repo' and page == open(os.path.join(env.root, 'index.html'), 'rb').read(), 'GET /index.html is the checkout')
        port = int(urllib.parse.urlsplit(env.base).port)
        conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)

        def raw(path):
            conn.request('GET', path)
            resp = conn.getresponse()
            body = resp.read()
            return resp.status, body

        status, body = raw('/scripts/offline_env/harness.py')
        check(status == 200 and b'def dispatch' in body, 'checkout file is served')
        status, body = raw('/../etc/passwd')
        check(status in (403, 404) and b'root:' not in body, 'parent path is not served (%s)' % status)
        status, body = raw('/%2e%2e/%2e%2e/etc/passwd')
        check(status in (403, 404) and b'root:' not in body, 'encoded parent path is not served (%s)' % status)
        status, body = raw('http://example.com/')
        check(status == 403 and b'example.com' not in body.lower(), 'absolute URL is not proxied (%s)' % status)
        conn.close()
        # Restore snapshot data.js so the browser check sees real data.
        shutil.copyfile(os.path.join(env.root, 'data.js'), os.path.join(env.snapshot, 'data.js'))

        class Fake:
            def __init__(self, url, method='GET'):
                self.request = type('Req', (), {'url': url, 'method': method, 'resource_type': 'other'})()
                self.done = None
                self.detail = None

            def fulfill(self, **kw):
                self.done = 'fulfill'
                self.detail = kw

            def abort(self, error=None):
                self.done = 'abort'
                self.detail = error

            def continue_(self, **kw):
                self.done = 'continue'
                self.detail = kw

        log = RequestLog(None)
        tile = Fake('https://tile.openstreetmap.org/0/0/0.png')
        dispatch(tile, env, log)
        check(tile.done == 'fulfill' and tile.detail['body'] == BLANK_PNG, 'tile route returns the blank png')
        live = Fake('https://helpmap.uk/stamp.js')
        dispatch(live, env, log)
        check(live.done == 'fulfill' and live.detail['headers']['x-offline-env'] == 'snapshot', 'helpmap.uk/stamp.js is the local snapshot')
        page_route = Fake('https://www.helpmap.uk/index.html')
        dispatch(page_route, env, log)
        check(page_route.done == 'fulfill' and b'helpmap.uk' in page_route.detail['body'], 'helpmap.uk/index.html is the local file')
        outside = Fake('https://api.postcodes.io/postcodes/BN17%205LF')
        dispatch(outside, env, log)
        check(outside.done == 'abort' and log.external_urls() == [outside.request.url], 'postcodes.io is logged and aborted')
        try:
            log.assert_clean()
            check(False, 'assert_clean should fail after an external request')
        except ExternalRequest:
            check(True, 'assert_clean fails after an external request')
        log.events.clear()

        if not use_browser:
            print('browser check skipped')
        else:
            _browser_check(env, check)
    finally:
        env.close()

    if failures:
        print('SELF-CHECK FAILED')
        for why in failures:
            print(' -', why)
        return 1
    print('SELF-CHECK OK')
    return 0


def _browser_check(env, check):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('browser check skipped (playwright not installed)')
        return
    with sync_playwright() as pw:
        try:
            browser = launch(pw)
        except Exception as exc:
            print('browser check skipped (%s)' % str(exc).splitlines()[0][:180])
            return
        routed = offline_context(browser, offline=env, viewport={'width': 390, 'height': 844})
        try:
            page = routed.new_page()
            resp = page.goto(env.helpmap + '/?nocount', wait_until='domcontentloaded', timeout=30000)
            header = (resp.headers.get('x-offline-env') if resp else '') or ''
            check(header in ('repo', 'snapshot'), 'https://helpmap.uk answered locally (%s)' % header)
            page.wait_for_function(
                """()=>{try{const n=(window.FB_DATA&&FB_DATA.items&&FB_DATA.items.length)||(typeof items!=='undefined'?items.length:0);return n>100}catch(e){return false}}""",
                timeout=30000)
            digest = page.evaluate("""async()=>{const r=await fetch('data.js');const b=await r.arrayBuffer();
              const d=await crypto.subtle.digest('SHA-256', b);return {tag:r.headers.get('x-offline-env'),
              hex:[...new Uint8Array(d)].map(x=>x.toString(16).padStart(2,'0')).join('')}}""")
            want = hashlib.sha256(open(os.path.join(env.snapshot, 'data.js'), 'rb').read()).hexdigest()
            check(digest['tag'] == 'snapshot' and digest['hex'] == want, 'page data.js hash matches the snapshot')
            page.wait_for_function(
                "document.querySelectorAll('#map .leaflet-tile-loaded').length>0",
                timeout=15000)
            tiles = routed.log.of('tile')
            check(len(tiles) > 0 and all(is_tile_host(_host(t['url'])) for t in tiles),
                  'map tiles were stubbed (%d)' % len(tiles))
            check(not routed.log.external_urls(), 'page load made no external request')
            # A route registered after the factory wins. Fulfil locally so this is not a failure.
            routed.context.route(
                'https://api.postcodes.io/**',
                lambda route: route.fulfill(status=200, content_type='application/json', body=b'{"status":200,"result":{}}'))
            status = page.evaluate("""async()=>{const r=await fetch('https://api.postcodes.io/postcodes/BN17%205LF');return r.status}""")
            check(status == 200 and not routed.log.external_urls(), 'a later route can answer postcodes.io locally')
            probe = 'https://example.com/offline-env-probe'
            blocked = False
            try:
                page.goto(probe, timeout=5000)
            except Exception:
                blocked = True
            check(blocked and routed.log.external_urls() == [probe], 'example.com was blocked and logged')
            routed.log.forget(probe)
            routed.log.assert_clean()
            check(True, 'forgetting the probe leaves the log clean')
        finally:
            routed.close(check=False)
            browser.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline helpmap.uk harness')
    sub = parser.add_subparsers(dest='cmd')
    serve_p = sub.add_parser('serve', help='serve the checkout on loopback until signalled')
    serve_p.add_argument('--host', default='127.0.0.1')
    serve_p.add_argument('--port', type=int, default=0)
    serve_p.add_argument('--root', default=None)
    serve_p.add_argument('--state', default=None)
    serve_p.add_argument('--log', default=None)
    sub.add_parser('check-log', help='exit 1 when the log contains an external request').add_argument('--log', required=True)
    check_p = sub.add_parser('self-check', help='prove the harness without contacting a live host')
    check_p.add_argument('--no-browser', action='store_true')
    # Also accept --self-check on the program itself, which run.sh uses.
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    if args.self_check or args.cmd == 'self-check':
        raise SystemExit(_self_check(use_browser=not args.no_browser))
    if args.cmd == 'check-log':
        raise SystemExit(assert_log_clean(args.log))
    if args.cmd == 'serve':
        _serve_cli(args)
        return
    parser.print_help()
    raise SystemExit(2)


if __name__ == '__main__':
    main()
