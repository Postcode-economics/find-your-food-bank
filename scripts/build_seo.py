"""Static, crawlable landing pages for Google (Dean 22 Oct 2026, free search boost).
Reads the published data (data.full.js, access.js, warmspaces.js) and writes:
  food-banks/index.html, food-banks/<area>/index.html, warm-spaces/..., sitemap.xml, robots.txt, 404.html.
Areas = local authority (postcodes.io admin_district for each service's own postcode), cached in
overrides/district_cache.json so refresh runs only look up new postcodes. Real data only: nothing is invented;
a field missing in the data is simply not shown. Never touches index.html or the map."""
import html, json, os, re, sys, urllib.request, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = 'https://helpmap.uk'
CACHE = os.path.join(ROOT, 'overrides', 'district_cache.json')
ORD = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
DN = {'mon': 'Mon', 'tue': 'Tue', 'wed': 'Wed', 'thu': 'Thu', 'fri': 'Fri', 'sat': 'Sat', 'sun': 'Sun'}
E = lambda s: html.escape(str(s or ''), quote=True)
LEGAL = ('<div class="legal"><p>helpmap.uk is a free guide compiled from publicly available information. While we aim to keep it '
         'accurate, details can change, so please confirm with the service before visiting. We are not affiliated with the services '
         'listed and cannot accept liability for any loss arising from use of this information. In an emergency, please call '
         '<a href="tel:999">999</a>.</p><p><a href="/faq.html">How we keep it up to date</a> · <a href="/shelters/">Shelters by area</a> · <a href="/terms.html">Terms of use</a> · <a href="/privacy.html">Privacy &amp; data protection</a> · '
         '<a href="/accessibility.html">Accessibility</a> · <a href="mailto:hello@helpmap.uk?subject=Report%20a%20mistake%20on%20helpmap.uk">Report a mistake</a></p></div>')
CSS = ('.ref{margin:4px 0}.opens{display:inline-block;font-weight:700;background:#e3f2fd;color:#0d47a1;padding:2px 8px;border-radius:8px;margin:4px 0}body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#13233f;background:#fff}'
       'main,header,footer{max-width:760px;margin:0 auto;padding:0 16px}header{padding-top:14px}'
       'a{color:#0b5cad}h1{font-size:1.5rem;line-height:1.25;margin:.4em 0}.top a{font-weight:700;text-decoration:none}'
       '.cta{display:inline-block;background:#13233f;color:#fff;padding:12px 18px;border-radius:10px;font-weight:700;text-decoration:none;margin:6px 0 14px;min-height:20px}'
       '.call{border-left:6px solid #c62828;background:#fff4f4;padding:10px 12px;margin:10px 0;font-weight:700}'
       'ul.s{list-style:none;padding:0;margin:0}ul.s>li{border:1px solid #d9dee7;border-radius:12px;padding:12px;margin:10px 0}'
       '.n{font-weight:700;font-size:1.05rem}.tag{display:inline-block;font-size:.85rem;font-weight:700;padding:2px 8px;border-radius:8px;background:#e8f5e9;color:#1b5e20;margin:4px 0}'
       '.tag.v{background:#fff3e0;color:#8a4b00}.sub{font-size:.9rem;color:#555}.t{margin:4px 0;font-size:.95rem}.t td{padding:0 10px 0 0;vertical-align:top}'
       'ul.a{columns:2;padding-left:18px}ul.a li{margin:4px 0}footer{font-size:14px;color:#555;padding-bottom:30px;margin-top:20px;border-top:1px solid #d9dee7}'
       '@media(max-width:400px){ul.a{columns:1}}')

def load_js(name, var):
    s = open(os.path.join(ROOT, name), encoding='utf-8').read()
    return json.loads(s[s.index('=') + 1:].strip().rstrip(';'))

def slug(s):
    s = s.lower().replace('&', 'and')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')

def norm_pc(p): return re.sub(r'\s+', ' ', (p or '').strip().upper())

def lookup(pcs, cache, fetch=True):
    todo = [p for p in pcs if p and p not in cache]
    if fetch:
        for i in range(0, len(todo), 100):
            body = json.dumps({'postcodes': todo[i:i + 100], 'filter': 'postcode,admin_district'}).encode()
            req = urllib.request.Request('https://api.postcodes.io/postcodes', body, {'Content-Type': 'application/json', 'User-Agent': 'helpmap.uk build'})
            try:
                res = json.load(urllib.request.urlopen(req, timeout=30))['result']
            except Exception as e:
                print('postcodes.io lookup failed, using cache only:', e); break
            for r in res:
                if r['result'] and r['result'].get('admin_district'):
                    cache[r['query']] = r['result']['admin_district']
    return cache

def hours_fb(i):
    ot = i.get('opening_times') or {}
    st = ot.get('structured') if ot.get('status') == 'TIMES_FOUND' else None
    if not st: return '<div class="sub">Call for opening times</div>'
    rows = ''.join('<tr><td>%s</td><td>%s</td></tr>' % (DN[d], ', '.join('%s–%s' % (a, b) for a, b in st[d])) for d in ORD if st.get(d))
    return '<table class="t">%s</table>' % rows if rows else '<div class="sub">Call for opening times</div>'

def hours_ws(i):
    h = i.get('hours') or {}
    rows = ''.join('<tr><td>%s</td><td>%s</td></tr>' % (E(d), E(v)) for d, v in h.items() if v)
    return '<table class="t">%s</table>' % rows if rows else '<div class="sub">Call for opening times</div>'

def shelter_public(i):
    """Same rule as the map: no stale/ended/closed entries, and no OpenStreetMap-only entry (must have own-site evidence)."""
    if i.get('stale') or i.get('ended') or i.get('flag_closed') or not i.get('postcode'): return False
    if i.get('source') == 'OpenStreetMap' and not (i.get('evidence_url') or i.get('sign_url')): return False
    return True

ACC = {'referral_only': 'Referral only', 'self_referral': 'Self-referral', 'open_access': 'Open access'}

def card_sh(i):
    tag = '<div class="tag">Shelter</div>'
    if i.get('tier') == 'unverified': tag += ' <div class="tag v">Unverified – call before you go</div>'
    acc = ACC.get(i.get('access_type') or '')
    ref = ''
    if acc or i.get('referral'):
        rt = re.sub(r'^\s*(referral only|self[- ]referral|open access)\s*[:.–-]?\s*', '', i.get('referral') or '', flags=re.I) if i.get('referral') != 'Not stated' else ''
        ref = '<div class="ref"><b>%s</b>%s</div>' % (E(acc or 'Referral'), (': ' + E(rt)) if rt else '')
        if i.get('access_type') == 'referral_only': ref += '<div class="sub">You need a referral before you go, usually from an outreach team, day centre or the council.</div>'
    opens = ''
    if i.get('upcoming') or (i.get('scheme_dates') and str(i['scheme_dates']).startswith('Opens')):
        opens = '<div class="opens">%s</div>' % E(i.get('scheme_dates') or ('Opens ' + i.get('scheme_start', '')))
    elif i.get('scheme_dates'):
        opens = '<div class="sub">Scheme dates: %s</div>' % E(i['scheme_dates'])
    h = (i.get('hours') or '').strip() if isinstance(i.get('hours'), str) else ''
    hrs = '<div class="t">%s</div>' % E(h) if h else '<div class="sub"><a href="/faq.html#times">Call for opening times</a></div>'
    note = '<div class="sub">%s</div>' % E(i['postcode_note']) if i.get('postcode_note') else ''
    web = '<div><a href="%s" rel="noopener nofollow">Website</a></div>' % E(i['website']) if i.get('website') else ''
    return ('<li><div class="n">%s</div>%s%s<div>%s</div>%s%s%s%s%s%s<div class="sub">Times change, call before you go.</div></li>'
            % (E(i['name']), tag, opens, E(i.get('address')), note, phone_html(i.get('phone'), i.get('phone_label')), web, sh_contact(i), ref, hrs))

def ws_fallback(i):
    if i.get('tel') or not i.get('council_phone'): return ''
    return '<div class="ref">No number for the venue itself. Council main number (%s): <a href="tel:%s">%s</a></div>' % (E(i['council']), E(re.sub(r'[^0-9+]', '', i['council_phone'])), E(i['council_phone']))

def sh_contact(i):
    """Email, council referral line, and national fallbacks when there is no direct number (overrides/shelters_contacts.json)."""
    o = ''
    if i.get('email'): o += '<div>Email: <a href="mailto:%s">%s</a></div>' % (E(i['email']), E(i['email']))
    if i.get('council_phone'):
        o += '<div class="ref"><b>How to get a place</b>: referral via %s. Council homeless line: %s' % (E(i['council']), phone_html(i['council_phone'])[5:-6].replace('Phone: ', ''))
        if i.get('council_ooh') and i['council_ooh'] != i['council_phone']:
            o += ' (out of hours <a href="tel:%s">%s</a>)' % (E(re.sub(r'[^0-9+]', '', i['council_ooh'])), E(i['council_ooh']))
        o += '</div>'
    if not i.get('tel'):
        o += ('<div class="ref"><b>No direct number.</b> Help tonight: Shelter national helpline (not this venue) <a href="tel:08088004444">0808 800 4444</a>, '
              'or your local council&#39;s homeless team. Someone sleeping rough: <a href="https://thestreetlink.org.uk/" rel="noopener">StreetLink</a></div>')
    return o

def phone_html(p, label=''):
    if not p: return ''
    extra = ''
    if label:
        shown = label if re.search(r'(number|line)$', label, re.I) else 'Number for ' + label
        extra = ' <span class="sub">%s</span>' % E(shown)
    return '<div>Phone: <a href="tel:%s">%s</a>%s</div>' % (E(re.sub(r'[^0-9+]', '', p)), E(p), extra)

def card_fb(i, acc):
    a = acc.get(i['id'], 'unconfirmed')
    tag = ('<div class="tag v">Foodbank voucher needed – no walk-ins without a referral</div>' if a == 'voucher'
           else '<div class="tag">Food bank – get food here</div>')
    extra = '<div class="sub">Walk-in not confirmed – call before you go</div>' if a == 'unconfirmed' else ''
    web = '<div><a href="%s" rel="noopener nofollow">Website</a></div>' % E(i['website']) if i.get('website') else ''
    return ('<li><div class="n">%s</div>%s%s<div>%s</div>%s%s%s<div class="sub">Times change, call before you go.</div></li>'
            % (E(i['name']), tag, extra, E(i.get('address')), phone_html(i.get('phone')) + ws_fallback(i), hours_fb(i), web))

def card_ws(i):
    web = '<div><a href="%s" rel="noopener nofollow">Website</a></div>' % E(i['website']) if i.get('website') else ''
    tag = '<div class="tag">Warm space</div>'
    if i.get('tier') == 'unverified': tag += ' <div class="tag v">Unverified – call before you go</div>'
    opens = ''
    if i.get('upcoming') and (i.get('scheme_dates') or i.get('scheme_start')):
        opens = '<div class="opens">%s</div>' % E(i.get('scheme_dates') if str(i.get('scheme_dates', '')).startswith('Opens') else 'Opens ' + i['scheme_start'])
    elif i.get('scheme_dates'):
        opens = '<div class="sub">Scheme dates: %s</div>' % E(i['scheme_dates'])
    ref = ''
    if i.get('booking') and i['booking'] != 'Not stated': ref += '<div class="ref"><b>%s</b></div>' % E(i['booking'])
    if 'referr' in (i.get('notes') or '').lower(): ref += '<div class="ref"><b>Referral:</b> %s</div>' % E(i['notes'])
    hrs = '<div class="sub">Times unknown – call before you go</div>' if i.get('call_check') else hours_ws(i)
    return ('<li><div class="n">%s</div>%s%s<div>%s</div>%s%s%s%s<div class="sub">Times change, call before you go.</div></li>'
            % (E(i['name']), tag, opens, E(i.get('address')), phone_html(i.get('phone')), hrs, ref, web))

SH_CREDIT = ''
SH_SRC = [('homeless.org.uk', 'Homeless Link', 'https://homeless.org.uk/homeless-england/'), ('openstreetmap.org', 'OpenStreetMap contributors', 'https://www.openstreetmap.org/copyright'),
          ('salvationarmy.org.uk', 'The Salvation Army', 'https://www.salvationarmy.org.uk/'), ('simoncommunity.org', 'Simon Community', 'https://simoncommunity.org/')]
def shelter_credit(items):
    """Dean 25 Oct: footers credit the shelter sources actually used in shelters.js (data-driven)."""
    urls = ' '.join(str(i.get('source_url') or '') + ' ' + str(i.get('hours_source') or '') for i in items)
    used = ['<a href="%s" rel="noopener">%s</a>' % (u, n) for d, n, u in SH_SRC if d in urls]
    return (' and, for shelters, ' + ', '.join(used) + ' and providers’ own websites') if used else ''

def page(path, title, desc, body, crumbs, updated):
    url = SITE + path
    ld = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': n + 1, 'name': nm, 'item': SITE + p} for n, (nm, p) in enumerate(crumbs)]}
    return ('<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>%s</title><meta name="description" content="%s"><link rel="canonical" href="%s">'
            '<link rel="icon" href="/favicon.ico?v=1" sizes="any"><link rel="apple-touch-icon" href="/apple-touch-icon.png?v=1"><link rel="icon" href="/icon.svg" type="image/svg+xml"><link rel="icon" href="/icon-192.png" sizes="192x192" type="image/png"><link rel="icon" href="/icon-48.png" sizes="48x48" type="image/png"><link rel="manifest" href="/site.webmanifest">'
            '<meta property="og:type" content="website"><meta property="og:site_name" content="helpmap.uk"><meta property="og:title" content="%s">'
            '<meta property="og:description" content="%s"><meta property="og:url" content="%s"><meta property="og:image" content="https://helpmap.uk/og_launch.png">'
            '<meta name="twitter:card" content="summary_large_image"><style>%s</style>'
            '<script type="application/ld+json">%s</script></head><body><header><div class="top"><a href="/">helpmap.uk</a></div></header>'
            '<main>%s</main><footer><p>Information last updated %s. Data: <a href="https://www.givefood.org.uk/" rel="noopener">Give Food</a>, '
            'the <a href="https://www.foodaidnetwork.org.uk/" rel="noopener">Independent Food Aid Network</a>, local warm space directories%s. '
            'Areas from <a href="https://postcodes.io/" rel="noopener">postcodes.io</a> (contains OS data © Crown copyright and database right 2026).</p>%s</footer></body></html>\n'
            % (E(title), E(desc), url, E(title), E(desc), url, CSS, json.dumps(ld, ensure_ascii=False).replace('</', '<\\/'), body, E(updated), SH_CREDIT, LEGAL))

import beacon  # analytics beacon on every generated page (25 Oct 2026)
def write(rel, text, out):
    text = beacon.inject(text)
    p = os.path.join(out, rel.lstrip('/'))
    if p.endswith('/'): p += 'index.html'
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8').write(text)

def section(kind, items, cache, updated, out, card):
    label, base, noun = kind
    groups = {}
    for i in items:
        d = cache.get(norm_pc(i.get('postcode')))
        if d: groups.setdefault(d, []).append(i)
    urls = []
    for d, lst in sorted(groups.items()):
        lst.sort(key=lambda x: x['name'].lower())
        path = '/%s/%s/' % (base, slug(d))
        n = len(lst)
        title = '%s in %s – free help near you' % (label, d)
        desc = '%d %s in %s with addresses, phone numbers and opening times. Checked three times a day. Free, no sign-up. Always call before you go.' % (n, noun if n != 1 else noun.rstrip('s'), d)
        body = ('<h1>%s in %s</h1><p>%d %s listed in the %s area, taken from the same checked data as the helpmap.uk map. '
                'Details can change, so please call before you go.</p><a class="cta" href="/?q=%s">Open on the map</a>'
                '<p class="chk3"><a href="/faq.html">Checked three times daily</a></p><div class="call">Always call before you go</div><ul class="s">%s</ul><!--xlinks:%s--><p><a href="/%s/">All areas</a></p>'
                % (E(label), E(d), n, noun if n != 1 else noun.rstrip('s'), E(d), E(urllib.request.quote(lst[0]['postcode'])), ''.join(card(i) for i in lst), slug(d), base))
        write(path, page(path, title, desc, body, [('helpmap.uk', '/'), (label, '/%s/' % base), (d, path)], updated), out)
        urls.append(path)
    links = ''.join('<li><a href="/%s/%s/">%s</a> (%d)</li>' % (base, slug(d), E(d), len(l)) for d, l in sorted(groups.items()))
    path = '/%s/' % base
    body = ('<h1>%s by area</h1><p>Free UK list of %d %s across %d council areas. Pick your area, or <a href="/">search the map by postcode</a>.</p>'
            '<ul class="a">%s</ul>' % (E(label), sum(len(l) for l in groups.values()), noun, len(groups), links))
    write(path, page(path, '%s by area – helpmap.uk' % label, 'Find %s near you in every UK council area. Checked three times a day. Free, no sign-up.' % noun, body,
                     [('helpmap.uk', '/'), (label, path)], updated), out)
    return [path] + urls

def build(out=ROOT, fetch=True):
    fb = load_js('data.full.js', 'FB_DATA'); acc = load_js('access.js', 'FB_ACCESS'); ws = load_js('warmspaces.js', 'WARMSPACES')
    fbi = [i for i in fb['items'] if i.get('kind') not in ('warehouse', 'dropoff') and i.get('postcode')]
    global SH_CREDIT
    sh = load_js('shelters.js', 'SHELTERS'); shi = [i for i in sh['items'] if shelter_public(i)]; SH_CREDIT = shelter_credit(sh['items'])
    wsi = [i for i in ws['items'] if not i.get('ended') and not i.get('stale') and i.get('postcode')]
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    lookup(sorted({norm_pc(i['postcode']) for i in fbi + wsi + shi}), cache, fetch)
    if out == ROOT:
        json.dump(dict(sorted(cache.items())), open(CACHE, 'w'), indent=0)
    for base in ('food-banks', 'warm-spaces', 'shelters'):   # drop pages for areas that no longer have any service
        d = os.path.join(out, base)
        if os.path.isdir(d):
            for sub in os.listdir(d):
                f = os.path.join(d, sub, 'index.html')
                if os.path.exists(f): os.remove(f)
    urls = section(('Food banks', 'food-banks', 'food banks'), fbi, cache, fb['fetched'], out, lambda i: card_fb(i, acc))
    urls += section(('Warm spaces', 'warm-spaces', 'warm spaces'), wsi, cache, ws['updated'], out, card_ws)
    urls += section(('Homeless shelters', 'shelters', 'homeless shelters'), shi, cache, sh['updated'], out, card_sh)
    XL = [('food-banks', 'Food banks'), ('warm-spaces', 'Warm spaces'), ('shelters', 'Homeless shelters')]
    have = set(u for u in urls)
    for u in urls:   # cross-link the same area's food bank / warm space / shelter pages
        parts = u.strip('/').split('/')
        if len(parts) != 2: continue
        p = os.path.join(out, parts[0], parts[1], 'index.html'); s = open(p, encoding='utf-8').read()
        links = ['<a href="/%s/%s/">%s</a>' % (b_, parts[1], lab) for b_, lab in XL if b_ != parts[0] and '/%s/%s/' % (b_, parts[1]) in have]
        html_ = '<p class="xl">Also in this area: %s</p>' % ' · '.join(links) if links else ''
        open(p, 'w', encoding='utf-8').write(s.replace('<!--xlinks:%s-->' % parts[1], html_))
    for d in ('food-banks', 'warm-spaces', 'shelters'):   # remove now-empty area folders
        for sub in os.listdir(os.path.join(out, d)):
            p = os.path.join(out, d, sub)
            if os.path.isdir(p) and not os.listdir(p): os.rmdir(p)
    lm = {'/': fb['fetched']}
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in ['/'] + urls + ['/faq.html', '/privacy.html', '/terms.html', '/accessibility.html']:
        d = ws['updated'] if u.startswith('/warm-spaces') else sh['updated'] if u.startswith('/shelters') else fb['fetched']
        sm.append('<url><loc>%s%s</loc><lastmod>%s</lastmod></url>' % (SITE, u, d))
    sm.append('</urlset>')
    open(os.path.join(out, 'sitemap.xml'), 'w').write('\n'.join(sm) + '\n')
    open(os.path.join(out, 'robots.txt'), 'w').write('User-agent: *\nAllow: /\nDisallow: /logs/\nDisallow: /reports/\nDisallow: /overrides/\nDisallow: /scripts/\nDisallow: /tests/\n\nSitemap: %s/sitemap.xml\n' % SITE)
    body = ('<h1>Page not found</h1><p>Sorry, that page isn’t here. It may have moved.</p><a class="cta" href="/">Open the helpmap.uk map</a>'
            '<p><a href="/food-banks/">Food banks by area</a> · <a href="/warm-spaces/">Warm spaces by area</a> · <a href="/shelters/">Shelters by area</a></p>')
    open(os.path.join(out, '404.html'), 'w').write(beacon.inject(page('/404.html', 'Page not found – helpmap.uk', 'Page not found.', body, [('helpmap.uk', '/')], fb['fetched']).replace('<link rel="canonical" href="https://helpmap.uk/404.html">', '<meta name="robots" content="noindex">')))
    print('seo pages: %d (+ sitemap, robots, 404)' % len(urls))
    return urls

if __name__ == '__main__':
    build(fetch='--offline' not in sys.argv)
