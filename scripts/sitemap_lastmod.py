"""Per-URL sitemap <lastmod>: the date that page's meaningful content last changed.

Google was seeing every URL stamped with today's date on each refresh, which
weakens crawl signals. This module hashes each page after stripping per-run
noise (Last checked, map-data stamps, JSON-LD dateModified, cache-busting
query strings, live counts, 'Updated' / 'Information last updated' lines) and
only advances lastmod when that hash changes.

Fail-safe: if a hash or previous date is missing or unreadable, keep the
previous lastmod instead of bumping. New URLs (no previous lastmod) get today.

Memory is stored in overrides/page_dates.json under the '_sitemap' key (already
committed by every refresh). Entries are public path, a short content hash and
a YYYY-MM-DD date only — no listing text or private data.
"""
import datetime, hashlib, json, os, re

SITE = 'https://helpmap.uk'
STORE_KEY = '_sitemap'
PAGE_DATES = ('overrides', 'page_dates.json')

# Per-run or baked stamp text that is not a real content change.
_STRIP_SCRIPT_LD = re.compile(r'<script type="application/ld\+json".*?</script>', re.S | re.I)
_STRIP_MAPCHK = re.compile(r'<!--mapchk(?:-cy|js)?-->.*?<!--/mapchk(?:js)?-->', re.S)
_STRIP_UPD = re.compile(r'<p class="upd">[^<]*</p>')
_STRIP_MAPCHK_P = re.compile(r'<p class="mapchk"[^>]*>[^<]*</p>')
_STRIP_COUNTS = re.compile(r'(<span data-n="[^"]+">)[^<]*')
_STRIP_FRESH = re.compile(r'(<a id="freshtxt"[^>]*>)[^<]*')
_STRIP_INFO = re.compile(
    r'Information last updated\s+\d{1,2}\s+\w+\s+\d{4}(?:,\s*\d{2}:\d{2})?\s*\.',
    re.I,
)
_STRIP_CHECKED = re.compile(
    r'(Last checked:</b>\s*)\d{1,2}\s+\w+\s+\d{4}',
    re.I,
)
_STRIP_QV = re.compile(r'\?v=[^"\'\s>]*')
_STRIP_DATERUN = re.compile(r' data-run="[^"]*"')
_STRIP_ISO = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)?')
_DAY = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')


def url_of(rel):
    if rel == 'index.html' or rel == '/':
        return SITE + '/'
    if rel.endswith('/index.html'):
        return SITE + '/' + rel[:-len('index.html')]
    if rel.startswith('/'):
        return SITE + rel
    return SITE + '/' + rel


def meaningful_hash(s):
    """Stable hash of a page, ignoring refresh stamps and Last checked dates."""
    x = s or ''
    x = _STRIP_SCRIPT_LD.sub('', x)
    x = _STRIP_MAPCHK.sub('', x)
    x = _STRIP_UPD.sub('', x)
    x = _STRIP_MAPCHK_P.sub('', x)
    x = _STRIP_COUNTS.sub(r'\1', x)
    x = _STRIP_FRESH.sub(r'\1', x)
    x = _STRIP_INFO.sub('Information last updated.', x)
    x = _STRIP_CHECKED.sub(r'\1', x)
    x = _STRIP_QV.sub('', x)
    x = _STRIP_DATERUN.sub('', x)
    x = _STRIP_ISO.sub('', x)
    x = re.sub(r'\s+', ' ', x).strip()
    return hashlib.sha256(x.encode('utf-8')).hexdigest()[:16]


def valid_day(s, today=None):
    m = _DAY.match(str(s or '').strip())
    if not m:
        return None
    try:
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    if today and d > today:
        return None
    return d.isoformat()


def read_sitemap_lastmods(path):
    """loc -> YYYY-MM-DD from an existing sitemap.xml; empty on any error."""
    out = {}
    try:
        text = open(path, encoding='utf-8').read()
    except Exception:
        return out
    try:
        for block in re.findall(r'<url>(.*?)</url>', text, re.S | re.I):
            loc = re.search(r'<loc>\s*([^<\s]+)\s*</loc>', block, re.I)
            mod = re.search(r'<lastmod>\s*([^<\s]+)\s*</lastmod>', block, re.I)
            if not loc:
                continue
            day = valid_day((mod.group(1) if mod else '')[:10])
            if day:
                out[loc.group(1).strip()] = day
    except Exception:
        return {}
    return out


def load_store(dates):
    raw = (dates or {}).get(STORE_KEY) or {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for url, rec in raw.items():
        if not isinstance(url, str) or not url.startswith(SITE):
            continue
        if not isinstance(rec, dict):
            continue
        h = rec.get('hash')
        day = valid_day(rec.get('lastmod'))
        if isinstance(h, str) and re.fullmatch(r'[0-9a-f]{8,64}', h) and day:
            out[url] = {'hash': h, 'lastmod': day}
    return out


def lastmod_for(url, content_hash, store, previous, today, bump=True):
    """Pick a lastmod. If bump is False (build_seo's first pass), never advance."""
    today_s = today.isoformat() if isinstance(today, datetime.date) else valid_day(today)
    rec = store.get(url) if store else None
    if rec and rec.get('hash') == content_hash and valid_day(rec.get('lastmod')):
        return rec['lastmod']
    if bump and rec and rec.get('hash') and rec.get('hash') != content_hash and today_s:
        return today_s
    prev = valid_day(previous.get(url) if previous else None)
    if prev:
        return prev
    if rec and valid_day(rec.get('lastmod')):
        return rec['lastmod']
    return today_s


def collect(root, rels, today, dates=None, bump=True):
    """Return (lastmods by url, store to persist). Fail-safe: never raises."""
    today = today if isinstance(today, datetime.date) else datetime.date.fromisoformat(str(today)[:10])
    previous = read_sitemap_lastmods(os.path.join(root, 'sitemap.xml'))
    store = load_store(dates)
    lastmods, new_store = {}, {}
    try:
        for rel in rels:
            url = url_of(rel)
            path = os.path.join(root, 'index.html' if rel in ('index.html', '/') else rel.lstrip('/'))
            if rel.endswith('/') and not rel.endswith('.html'):
                cand = os.path.join(root, rel.lstrip('/'), 'index.html')
                if os.path.exists(cand):
                    path = cand
            try:
                html = open(path, encoding='utf-8').read() if os.path.exists(path) else ''
                h = meaningful_hash(html) if html else None
            except Exception:
                h = None
            if not h:
                day = lastmod_for(url, None, store, previous, today, bump=False)
                lastmods[url] = day or today.isoformat()
                if url in store:
                    new_store[url] = store[url]
                continue
            day = lastmod_for(url, h, store, previous, today, bump=bump)
            lastmods[url] = day or today.isoformat()
            new_store[url] = {'hash': h, 'lastmod': lastmods[url]}
    except Exception:
        # Keep every previous lastmod we already knew; today only for missing URLs.
        lastmods, new_store = {}, dict(store)
        for rel in rels:
            url = url_of(rel)
            lastmods[url] = previous.get(url) or (store.get(url) or {}).get('lastmod') or today.isoformat()
    return lastmods, new_store


def write_urlset(root, rels, today, dates=None, bump=True, persist=True):
    """Write sitemap.xml for rels. Updates dates[STORE_KEY] when persist is True."""
    dates = dates if dates is not None else {}
    lastmods, store = collect(root, rels, today, dates=dates, bump=bump)
    if persist:
        dates[STORE_KEY] = store
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for rel in rels:
        url = url_of(rel)
        lines.append('<url><loc>%s</loc><lastmod>%s</lastmod></url>' % (url, lastmods[url]))
    lines.append('</urlset>')
    open(os.path.join(root, 'sitemap.xml'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    return lastmods
