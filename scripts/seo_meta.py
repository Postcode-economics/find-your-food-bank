"""Bake the refresh time into every public page (fail-safe; run after stamp.py write).
- WebPage JSON-LD with dateModified on every page (block marked data-ld="page")
- Dataset JSON-LD on the home page (data-ld="dataset"), FAQPage JSON-LD on faq.html (data-ld="faq")
- the no-JS text of the home page's 'Updated today at HH:MM' line
- sitemap.xml lastmod for every page
- ?v=r<run time> on data.js, stamp.js and access.js in index.html (edge cache-bust).
Usage: python scripts/seo_meta.py"""
import datetime, glob, html, json, os, re
from zoneinfo import ZoneInfo
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SITE = 'https://helpmap.uk'
TOP = ['index.html', 'faq.html', 'terms.html', 'privacy.html', 'accessibility.html']

def lab(t):
    """Dean 25 Oct: the one date format on the site, '25 Oct 2026, 05:12' (UK time)."""
    return '%d %s, %s' % (t.day, t.strftime('%b %Y'), t.strftime('%H:%M'))

def stamp_layers(root=ROOT):
    s = json.loads(open(os.path.join(root, 'stamp.js')).read().split('=', 1)[1].rstrip().rstrip(';'))
    L = {k: datetime.datetime.fromisoformat(v['run']).astimezone(ZoneInfo('Europe/London')) for k, v in (s.get('layers') or {}).items()}
    return L

def put_info(s, rel, t, L):
    """'Information last updated <date>.' footers: the refresh time of that page's own layer (404/other: latest run)."""
    k = 'ws' if rel.startswith('warm-spaces/') else 'sh' if rel.startswith('shelters/') else 'fb' if rel.startswith('food-banks/') else None
    return re.sub(r'Information last updated [^.<]*\.', 'Information last updated %s.' % lab(L.get(k) or t), s)

def body_hash(s):
    import hashlib
    x = re.sub(r'<script type="application/ld\+json".*?</script>', '', s, flags=re.S)
    x = re.sub(r'<!--mapchk(?:-cy|js)?-->.*?<!--/mapchk(?:js)?-->', '', x, flags=re.S)
    x = re.sub(r'<p class="upd">[^<]*</p>', '', x); x = re.sub(r'(<span data-n="[^"]+">)[^<]*', r'\1', x)
    return hashlib.sha256(x.encode()).hexdigest()[:16]

def put_upd(s, rel, t, dates):
    """Policy pages' 'Last updated': set automatically when the page's own text changes (never hand-edited)."""
    if '<p class="upd">' not in s: return s
    h = body_hash(s); e = dates.get(rel)
    if not e or e.get('hash') != h: dates[rel] = e = {'hash': h, 'at': t.isoformat(timespec='seconds')}
    at = datetime.datetime.fromisoformat(e['at']).astimezone(ZoneInfo('Europe/London'))
    return re.sub(r'<p class="upd">[^<]*</p>', '<p class="upd">Last updated %s</p>' % lab(at), s, count=1)

def stamp(root=ROOT):
    s = json.loads(open(os.path.join(root, 'stamp.js')).read().split('=', 1)[1].rstrip().rstrip(';'))
    return datetime.datetime.fromisoformat(s['run']).astimezone(ZoneInfo('Europe/London'))

def pages(root=ROOT):
    out = [p for p in TOP if os.path.exists(os.path.join(root, p))]
    for base in ('food-banks', 'warm-spaces', 'shelters'):
        out += sorted(os.path.relpath(p, root) for p in glob.glob(os.path.join(root, base, '**', 'index.html'), recursive=True))
    return out

def url_of(rel):
    if rel == 'index.html': return SITE + '/'
    if rel.endswith('/index.html'): return SITE + '/' + rel[:-len('index.html')]
    return SITE + '/' + rel

def ld(kind, obj):
    return '<script type="application/ld+json" data-ld="%s">%s</script>' % (kind, json.dumps(obj, ensure_ascii=False).replace('</', '<\\/'))

def put(text, kind, block):
    pat = re.compile(r'<script type="application/ld\+json" data-ld="%s">.*?</script>' % kind, re.S)
    if pat.search(text): return pat.sub(lambda m: block, text, count=1)
    return text.replace('</head>', block + '</head>', 1)

def title_of(text):
    m = re.search(r'<title>(.*?)</title>', text, re.S)
    return html.unescape(m.group(1).strip()) if m else 'helpmap.uk'

def dataset(iso):
    return {'@context': 'https://schema.org', '@type': 'Dataset', '@id': SITE + '/#dataset',
        'name': 'helpmap.uk: UK food banks, homeless shelters and warm spaces',
        'description': 'Free map data of UK food banks, homeless shelters and warm spaces, with addresses, phone numbers and opening times. '
                       'Every listing is checked three times a day against its source page, and a deep sweep three times a day looks for new places.',
        'url': SITE + '/', 'isAccessibleForFree': True, 'inLanguage': ['en-GB', 'cy'], 'spatialCoverage': {'@type': 'Place', 'name': 'United Kingdom'},
        'dateModified': iso, 'creator': {'@type': 'Organization', 'name': 'Postcode Economics', 'email': 'hello@helpmap.uk'},
        'publisher': {'@type': 'Organization', 'name': 'Postcode Economics', 'email': 'hello@helpmap.uk'},
        'temporalCoverage': '2026/..', 'measurementTechnique': 'Automated checks of each listing against its own or official source page, three times a day',
        'subjectOf': {'@type': 'WebPage', 'url': SITE + '/faq.html', 'name': 'How our information is kept up to date'},
        'isBasedOn': [
            {'@type': 'CreativeWork', 'name': 'Give Food', 'url': 'https://www.givefood.org.uk/'},
            {'@type': 'CreativeWork', 'name': 'Independent Food Aid Network (IFAN)', 'url': 'https://www.foodaidnetwork.org.uk/'},
            {'@type': 'CreativeWork', 'name': 'Warm Welcome', 'url': 'https://www.warmwelcome.uk/'},
            {'@type': 'CreativeWork', 'name': 'Open Innovations warm spaces', 'url': 'https://open-innovations.org/'},
            {'@type': 'CreativeWork', 'name': 'Homeless Link', 'url': 'https://homeless.org.uk/homeless-england/'},
            {'@type': 'CreativeWork', 'name': 'OpenStreetMap', 'url': 'https://www.openstreetmap.org/', 'license': 'https://opendatacommons.org/licenses/odbl/'},
            {'@type': 'CreativeWork', 'name': 'postcodes.io (contains OS data © Crown copyright and database right 2026; Royal Mail, National Statistics and NRS data)',
             'url': 'https://postcodes.io/', 'license': 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/'}],
        # GSC 'Datasets' fixes (25 Oct 2026): sources are CreativeWork (a nested Dataset must itself carry description etc.);
        # license = our terms of use page (reuse terms in export/README.txt); distribution = the real public download files.
        'license': SITE + '/terms.html', 'keywords': ['food banks', 'homeless shelters', 'warm spaces', 'United Kingdom'],
        'distribution': [{'@type': 'DataDownload', 'encodingFormat': f, 'contentUrl': SITE + '/export/%s.%s' % (n, e)}
                         for n in ('foodbanks', 'shelters', 'warmspaces') for e, f in (('csv', 'text/csv'), ('json', 'application/json'))],
        'creditText': 'Data: Give Food, Independent Food Aid Network, Warm Welcome, Open Innovations, Homeless Link, council pages, OpenStreetMap contributors, postcodes.io (OGL v3.0). Map © OpenStreetMap contributors. Backup map: OpenFreeMap © OpenMapTiles. © MapTiler.'}

def faq_ld(text):
    sec = text.split('<section id="cy"')[0]
    qa = []
    for m in re.finditer(r'<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|</section>)', sec, re.S):
        q = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
        a = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', m.group(2)))).strip()
        a = re.sub(r' ([,.;:)])', r'\1', a)
        a = a.replace('( ', '(')
        qa.append({'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}})
    return {'@context': 'https://schema.org', '@type': 'FAQPage', 'inLanguage': 'en-GB', 'mainEntity': qa}

CYM = ['Ionawr', 'Chwefror', 'Mawrth', 'Ebrill', 'Mai', 'Mehefin', 'Gorffennaf', 'Awst', 'Medi', 'Hydref', 'Tachwedd', 'Rhagfyr']
CHK_JS = ("<script>(function(){var s=window.FB_STAMP;if(!s||!s.run)return;var m=s.run.match(/^(\\d{4})-(\\d\\d)-(\\d\\d)T(\\d\\d:\\d\\d)/);if(!m)return;"
          "var td=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/London'}).format(new Date()),same=(m[1]+'-'+m[2]+'-'+m[3])===td,d=+m[3],mo=+m[2]-1,"
          "EN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],"
          "CY=['Ionawr','Chwefror','Mawrth','Ebrill','Mai','Mehefin','Gorffennaf','Awst','Medi','Hydref','Tachwedd','Rhagfyr'];"
          "document.querySelectorAll('.mapchk').forEach(function(e){var cy=e.getAttribute('lang')==='cy';"
          "e.textContent=cy?('Gwiriwyd data’r map ddiwethaf '+(same?'heddiw, ':d+' '+CY[mo]+' '+m[1]+', ')+m[4]):('Map data last checked '+(same?'today, ':d+' '+EN[mo]+' '+m[1]+', ')+m[4]);e.setAttribute('data-run',s.run)})})()</script>")

def chk_line(t, cy=False):
    if cy: txt = 'Gwiriwyd data’r map ddiwethaf %d %s %d, %s' % (t.day, CYM[t.month - 1], t.year, t.strftime('%H:%M'))
    else: txt = 'Map data last checked %s' % lab(t)
    return '<p class="mapchk"%s data-run="%s">%s</p>' % (' lang="cy"' if cy else '', t.isoformat(timespec='seconds'), txt)

def content_stamp(root, name):
    import hashlib
    return 'h' + hashlib.sha256(open(os.path.join(root, name), 'rb').read()).hexdigest()[:12]

def put_chk(s, t, rel):
    """Baked 'Map data last checked' line(s) + a live updater from stamp.js (FAQ and town pages only)."""
    s = re.sub(r'<!--mapchk(?:-cy)?-->.*?<!--/mapchk-->', '', s, flags=re.S)
    s = re.sub(r'<!--mapchkjs-->.*?<!--/mapchkjs-->', '', s, flags=re.S)
    en = '<!--mapchk-->%s<!--/mapchk-->' % chk_line(t)
    if rel == 'faq.html':
        s = re.sub(r'(<p class="upd">Last updated [^<]*</p>)', lambda m: m.group(1) + en, s, count=1)
        s = re.sub(r'(<section id="cy"[^>]*>\s*<h1>.*?</h1>)', lambda m: m.group(1) + '<!--mapchk-cy-->%s<!--/mapchk-->' % chk_line(t, True), s, count=1, flags=re.S)
    else:
        s = s.replace('<p class="chk3">', en + '<p class="chk3">', 1)
    js = '<!--mapchkjs--><script src="/stamp.js?v=r%s"></script>%s<!--/mapchkjs-->' % (t.strftime('%Y%m%dT%H%M'), CHK_JS)
    return s.replace('</body>', js + '</body>', 1)

def swep_counts(root=ROOT):
    """Dean 25 Oct: SWEP figures on faq.html come from the data each run (never hand-edited)."""
    try:
        src = json.load(open(os.path.join(root, 'overrides', 'swep_sources.json')))
        st = json.load(open(os.path.join(root, 'logs', 'swep_status.json')))
        return {'swep-councils': len({x.get('council') for x in src if isinstance(x, dict) and x.get('council')}), 'swep-pages': st['sources'] if isinstance(st.get('sources'), int) else len(st.get('sources') or [])}
    except Exception:
        return {}

def put_counts(s, n):
    for k, v in n.items():
        s = re.sub(r'(<span data-n="%s">)[^<]*(</span>)' % re.escape(k), lambda m: m.group(1) + format(v, ',') + m.group(2), s)
    return s

DESC = {'privacy.html': 'Privacy and data protection at helpmap.uk: what information the map uses, what is kept, and your rights.',
        'terms.html': 'Terms of use for helpmap.uk, the free UK map of food banks, homeless shelters and warm spaces, and how the data may be reused.',
        'accessibility.html': 'Accessibility statement for helpmap.uk, the free UK map of food banks, homeless shelters and warm spaces, and how to report a problem.',
        'faq.html': 'How helpmap.uk works and keeps food bank, shelter and warm space details up to date, checked three times a day against each source.'}
OG_IMG, OG_ALT = SITE + '/og_launch.png', 'Free UK food bank, shelter and warm space map'
def _meta_content(s, attr, name):
    m = re.search(r'<meta %s="%s" content="([^"]*)"' % (attr, re.escape(name)), s)
    return html.unescape(m.group(1)) if m else None
def put_social(s, rel):
    """25 Oct 2026: every page carries title, description, canonical, og:* and twitter:* (added only where missing)."""
    head, sep, rest = s.partition('</head>')
    if not sep: return s
    title = title_of(s); url = url_of(rel) if rel != '404.html' else SITE + '/404.html'
    desc = _meta_content(head, 'name', 'description') or DESC.get(rel) or title
    esc = lambda x: html.escape(x, quote=True); add = []
    want = [('name', 'description', desc), ('property', 'og:type', 'website'), ('property', 'og:title', title), ('property', 'og:description', desc),
            ('property', 'og:url', url), ('property', 'og:image', OG_IMG), ('property', 'og:image:alt', OG_ALT), ('property', 'og:image:width', '1200'),
            ('property', 'og:image:height', '630'), ('property', 'og:locale', 'en_GB'), ('property', 'og:site_name', 'helpmap.uk'), ('name', 'twitter:card', 'summary_large_image'),
            ('name', 'twitter:title', title), ('name', 'twitter:description', desc), ('name', 'twitter:image', OG_IMG)]
    for a, n, v in want:
        if '<meta %s="%s"' % (a, n) not in head: add.append('<meta %s="%s" content="%s">' % (a, n, esc(v)))
    if 'rel="canonical"' not in head and rel != '404.html': add.append('<link rel="canonical" href="%s">' % esc(url))
    return head + ''.join(add) + sep + rest if add else s

def run(root=ROOT):
    t = stamp(root); iso = t.isoformat(timespec='seconds'); day = t.date().isoformat()
    ps = pages(root); L = stamp_layers(root); pd = os.path.join(root, 'overrides', 'page_dates.json')
    dates = json.load(open(pd)) if os.path.exists(pd) else {}
    if os.path.exists(os.path.join(root, '404.html')):
        p4 = os.path.join(root, '404.html'); s4 = open(p4, encoding='utf-8').read(); n4 = put_social(put_info(s4, '404.html', t, L), '404.html')
        if n4 != s4: open(p4, 'w', encoding='utf-8').write(n4)
    for rel in ps:
        p = os.path.join(root, rel); s = open(p, encoding='utf-8').read(); s0 = s
        s = put(s, 'page', ld('page', {'@context': 'https://schema.org', '@type': 'WebPage', 'url': url_of(rel), 'name': title_of(s),
                                        'dateModified': iso, 'isPartOf': {'@type': 'WebSite', 'url': SITE + '/'}}))
        if rel == 'index.html':
            # cache-bust the refreshed data files so the Cloudflare edge can't serve an old copy.
            # Batch 4 (27 Oct 2026): content-hash stamp (h + 12 hex of sha256), so the stamp only changes when the file does.
            # The home page defers these (data-hm, type=text/plain). Only the src value is rewritten and every other attribute
            # on the tag is kept, or a sweep would turn them back into scripts that run during parse.
            s = re.sub(r'(<script\b[^>]*\bsrc=")(data|stamp|access)\.js(?:\?v=[^"]*)?("[^>]*>\s*</script>)',
                       lambda m: '%s%s.js?v=%s%s' % (m.group(1), m.group(2), content_stamp(root, m.group(2) + '.js'), m.group(3)), s)
            s = put(s, 'dataset', ld('dataset', dataset(iso)))
            s = re.sub(r'(<a id="freshtxt"[^>]*>)[^<]*(</a>)', lambda m: m.group(1) + 'Updated %s' % lab(t) + m.group(2), s)
        if rel == 'faq.html': s = put_counts(s, swep_counts(root))
        s = put_info(s, rel, t, L)
        s = put_social(s, rel)
        if rel in TOP: s = put_upd(s, rel, t, dates)
        if rel == 'faq.html' or rel.startswith(('food-banks/', 'warm-spaces/', 'shelters/')) and rel.count('/') == 2:
            s = put_chk(s, t, rel)
        if rel == 'faq.html':
            s = put(s, 'faq', ld('faq', faq_ld(s)))
        if s != s0: open(p, 'w', encoding='utf-8').write(s)
    if os.path.isdir(os.path.dirname(pd)): json.dump(dates, open(pd, 'w'), indent=1, sort_keys=True)
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += ['<url><loc>%s</loc><lastmod>%s</lastmod></url>' % (url_of(r), day) for r in ps]
    open(os.path.join(root, 'sitemap.xml'), 'w').write('\n'.join(sm + ['</urlset>']) + '\n')
    print('seo_meta: %d pages stamped %s' % (len(ps), iso))
    return ps

if __name__ == '__main__':
    run()
    import sw_version; sw_version.sync()
    import beacon; print('beacon added to', beacon.inject_all(ROOT), 'pages')  # version.json + index build meta from sw.js (single source)
