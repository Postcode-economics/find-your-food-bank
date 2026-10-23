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

def stamp(root=ROOT):
    s = json.loads(open(os.path.join(root, 'stamp.js')).read().split('=', 1)[1].rstrip().rstrip(';'))
    return datetime.datetime.fromisoformat(s['run']).astimezone(ZoneInfo('Europe/London'))

def pages(root=ROOT):
    out = [p for p in TOP if os.path.exists(os.path.join(root, p))]
    for base in ('food-banks', 'warm-spaces'):
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
            {'@type': 'Dataset', 'name': 'Give Food', 'url': 'https://www.givefood.org.uk/'},
            {'@type': 'Dataset', 'name': 'Independent Food Aid Network (IFAN)', 'url': 'https://www.foodaidnetwork.org.uk/'},
            {'@type': 'Dataset', 'name': 'Warm Welcome', 'url': 'https://www.warmwelcome.uk/'},
            {'@type': 'Dataset', 'name': 'Open Innovations warm spaces', 'url': 'https://open-innovations.org/'},
            {'@type': 'Dataset', 'name': 'Homeless Link', 'url': 'https://homeless.org.uk/homeless-england/'},
            {'@type': 'Dataset', 'name': 'OpenStreetMap', 'url': 'https://www.openstreetmap.org/', 'license': 'https://opendatacommons.org/licenses/odbl/'},
            {'@type': 'Dataset', 'name': 'postcodes.io (contains OS data © Crown copyright and database right 2026; Royal Mail, National Statistics and NRS data)',
             'url': 'https://postcodes.io/', 'license': 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/'}],
        'creditText': 'Data: Give Food, Independent Food Aid Network, Warm Welcome, Open Innovations, Homeless Link, council pages, OpenStreetMap contributors, postcodes.io (OGL v3.0). Map © MapTiler © OpenStreetMap contributors.'}

def faq_ld(text):
    sec = text.split('<section id="cy"')[0]
    qa = []
    for m in re.finditer(r'<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|</section>)', sec, re.S):
        q = html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()
        a = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', m.group(2)))).strip()
        a = re.sub(r' ([,.;:)])', r'\1', a)
        qa.append({'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}})
    return {'@context': 'https://schema.org', '@type': 'FAQPage', 'inLanguage': 'en-GB', 'mainEntity': qa}

def run(root=ROOT):
    t = stamp(root); iso = t.isoformat(timespec='seconds'); day = t.date().isoformat()
    ps = pages(root)
    for rel in ps:
        p = os.path.join(root, rel); s = open(p, encoding='utf-8').read(); s0 = s
        s = put(s, 'page', ld('page', {'@context': 'https://schema.org', '@type': 'WebPage', 'url': url_of(rel), 'name': title_of(s),
                                        'dateModified': iso, 'isPartOf': {'@type': 'WebSite', 'url': SITE + '/'}}))
        if rel == 'index.html':
            # cache-bust the refreshed data files so the Cloudflare edge can't serve an old copy
            s = re.sub(r'<script src="(data|stamp|access)\.js(\?v=[^"]*)?"></script>', lambda m: '<script src="%s.js?v=r%s"></script>' % (m.group(1), t.strftime('%Y%m%dT%H%M')), s)
            s = put(s, 'dataset', ld('dataset', dataset(iso)))
            s = re.sub(r'(<a id="freshtxt"[^>]*>)[^<]*(</a>)', lambda m: m.group(1) + 'Updated %s at %s' % ('on %d %s' % (t.day, t.strftime('%B')), t.strftime('%H:%M')) + m.group(2), s)
        if rel == 'faq.html':
            s = put(s, 'faq', ld('faq', faq_ld(s)))
        if s != s0: open(p, 'w', encoding='utf-8').write(s)
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += ['<url><loc>%s</loc><lastmod>%s</lastmod></url>' % (url_of(r), day) for r in ps]
    open(os.path.join(root, 'sitemap.xml'), 'w').write('\n'.join(sm + ['</urlset>']) + '\n')
    print('seo_meta: %d pages stamped %s' % (len(ps), iso))
    return ps

if __name__ == '__main__':
    run()
