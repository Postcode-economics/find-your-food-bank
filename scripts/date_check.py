"""Block a publish when shown dates drift. Run on every PR, after each refresh, and on the deploy check.

Data times (map last updated, phones and hours checked) come from stamp.js and stamps/. The same
event shows the same time on every page. A page's own text date (FAQ, terms, privacy, accessibility)
comes from overrides/page_dates.json and is not moved by a data refresh. A card's checked, closed or
scheme date stays on that record.

Exit 1 if anything is wrong. `python scripts/date_check.py --table` prints the source of each kind of date.
"""
import datetime, json, os, re, sys
from zoneinfo import ZoneInfo
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import alert
import seo_meta as SM
LONDON = ZoneInfo('Europe/London')
MON = 'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec'
OK = re.compile(rf'^(?:\d{{1,2}} (?:{MON}) \d{{4}})(?:, \d\d:\d\d)?$')
FIND = re.compile(
    r'\b(?:today at \d\d:\d\d|today, \d\d:\d\d|heddiw, \d\d:\d\d|'
    r'\d{1,2} (?:January|February|March|April|June|July|August|September|October|November|December|'
    + MON + r'|Ionawr|Chwefror|Mawrth|Ebrill|Mehefin|Gorffennaf|Awst|Medi|Hydref|Tachwedd|Rhagfyr) \d{4}(?:, \d\d:\d\d)?|'
    r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?)\b')

def lab(t):
    return '%d %s, %s' % (t.day, t.strftime('%b %Y'), t.strftime('%H:%M'))

def london(iso):
    return datetime.datetime.fromisoformat(iso).astimezone(LONDON)

def visible(raw):
    s = re.sub(r'<script\b[^>]*>.*?</script>', ' ', raw, flags=re.S | re.I)
    s = re.sub(r'<style\b[^>]*>.*?</style>', ' ', s, flags=re.S | re.I)
    return re.sub(r'<[^>]+>', ' ', s)

def web_date(raw):
    m = re.search(r'"@type": "WebPage".*?"dateModified": "([^"]+)"', raw, re.S)
    if not m:
        m = re.search(r'"dateModified": "([^"]+)"', raw)
    return m.group(1) if m else None

def phrase(raw, pat):
    m = re.search(pat, visible(raw))
    return re.sub(r'\s+', ' ', m.group(1)).strip() if m else None

def rel_of(loc):
    path = loc.split('helpmap.uk', 1)[-1]
    if path in ('', '/'): return 'index.html'
    if path.endswith('/'): return path.strip('/') + '/index.html'
    return path.lstrip('/')

def problems(root=ROOT):
    """Every reason this tree must not be published. Empty means the dates agree."""
    out = []
    stamp_path = os.path.join(root, 'stamp.js')
    if not os.path.exists(stamp_path):
        return ['stamp.js is missing']
    raw = json.loads(open(stamp_path, encoding='utf-8').read().split('=', 1)[1].rstrip().rstrip(';'))
    layers = raw.get('layers') or {}
    if not layers:
        out.append('stamp.js has no layer times')
    for k, v in list(layers.items()) + ([('checked', raw['checked'])] if raw.get('checked') else []):
        try:
            want = lab(london(v['run']))
        except Exception:
            out.append('%s stamp time is unreadable (%s)' % (k, v.get('run'))); continue
        if v.get('label') != want:
            out.append('%s label %r is not its stamp time %s (a date was hard-coded)' % (k, v.get('label'), want))
    out += alert.date_problems(root)
    if not layers:
        return out
    times = {k: london(v['run']) for k, v in layers.items()}
    labels = {k: layers[k]['label'] for k in layers}
    newest = max(times, key=lambda k: times[k])
    fb = labels.get('fb') or labels[newest]
    checked = (raw.get('checked') or {}).get('label') or fb
    dates = {}
    dp = os.path.join(root, 'overrides', 'page_dates.json')
    if os.path.exists(dp):
        dates = json.load(open(dp, encoding='utf-8'))
    text_at = {}
    for rel in SM.TEXT_PAGES:
        if not os.path.exists(os.path.join(root, rel)): continue
        e = dates.get(rel) or {}
        if not e.get('at'):
            out.append('%s has no text-changed time in overrides/page_dates.json' % rel); continue
        text_at[rel] = london(e['at'])
        if lab(text_at[rel]) != lab(london(e['at'])):
            out.append('%s text date does not format' % rel)

    def data_label(rel):
        k = SM.layer_of(rel)
        return labels[k] if k in labels else labels[newest]

    pages = [p for p in SM.pages(root) if os.path.exists(os.path.join(root, p))]
    if os.path.exists(os.path.join(root, '404.html')):
        pages.append('404.html')
    seen = set()
    for rel in pages:
        seen.add(rel)
        s = open(os.path.join(root, rel), encoding='utf-8').read()
        if 'Updated today at' in s or 'heddiw,' in s or "'today, '" in s:
            out.append('%s still says today' % rel)
        vis = visible(s)
        vis = re.sub(r'Scheme dates:\s*Until \d{4}-\d{2}-\d{2}', 'Scheme dates: Until scheme-end', vis)
        for m in FIND.finditer(vis):
            if not OK.match(m.group(0)):
                out.append('%s: %s is not the approved format' % (rel, m.group(0)))
                break
        if rel in SM.TEXT_PAGES and rel in text_at:
            got = phrase(s, r'Last updated\s+(\d{1,2} \w+ \d{4}, \d\d:\d\d)')
            want = lab(text_at[rel])
            if got != want:
                out.append('%s text Last updated is %r, page_dates says %s' % (rel, got, want))
            dm = web_date(s)
            if dm and london(dm) != text_at[rel]:
                out.append('%s dateModified %s is not its text date %s' % (rel, dm, text_at[rel].isoformat(timespec='seconds')))
        if rel == 'faq.html':
            got = phrase(s, r'Map data last checked\s+(\d{1,2} \w+ \d{4}, \d\d:\d\d)')
            if got != labels[newest]:
                out.append('faq.html map last checked is %r, newest layer is %s' % (got, labels[newest]))
            cy = phrase(s, r'Gwiriwyd data’r map ddiwethaf\s+(\d{1,2} \w+ \d{4}, \d\d:\d\d)')
            if cy != labels[newest]:
                out.append('faq.html Welsh map line is %r, newest layer is %s' % (cy, labels[newest]))
        elif rel == 'index.html':
            got = phrase(s, r'Updated\s+(\d{1,2} \w+ \d{4}, \d\d:\d\d)')
            if got != labels[newest]:
                out.append('home header is %r, newest layer is %s' % (got, labels[newest]))
            mu = re.search(r'<span id="upd">([^<]*)</span>', s)
            mc = re.search(r'<span id="chk">([^<]*)</span>', s)
            if not mu or mu.group(1).strip() != fb:
                out.append('home footer food-bank time is %r, stamps/fb is %s' % (mu.group(1).strip() if mu else None, fb))
            if not mc or mc.group(1).strip() != 'checked ' + checked:
                out.append('home phone check is %r, checked stamp is %s' % (mc.group(1).strip() if mc else None, checked))
            if 'FB_STAMP.layers' not in s or 'FB_STAMP.checked' not in s:
                out.append('home page no longer reads the shared stamps')
            dm = web_date(s)
            if dm and london(dm) != times[newest]:
                out.append('home dateModified %s is not the newest layer %s' % (dm, times[newest].isoformat(timespec='seconds')))
        elif rel == '404.html' or rel.startswith(('food-banks/', 'warm-spaces/', 'shelters/')):
            want = labels[newest] if rel == '404.html' else data_label(rel)
            got = phrase(s, r'Information last updated\s+(\d{1,2} \w+ \d{4}, \d\d:\d\d)')
            if got != want:
                out.append('%s says %r, its data stamp is %s' % (rel, got, want))
            if 'Map data last checked' in s:
                mg = phrase(s, r'Map data last checked\s+(\d{1,2} \w+ \d{4}, \d\d:\d\d)')
                if mg != want:
                    out.append('%s map line is %r, its data stamp is %s' % (rel, mg, want))
            if rel != '404.html':
                dm = web_date(s)
                k = SM.layer_of(rel)
                if dm and k in times and london(dm) != times[k]:
                    out.append('%s dateModified %s is not the %s stamp' % (rel, dm, k))
    sm = os.path.join(root, 'sitemap.xml')
    if os.path.exists(sm):
        for loc, last in re.findall(r'<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>', open(sm, encoding='utf-8').read()):
            rel = rel_of(loc)
            if rel in text_at:
                want = text_at[rel].date().isoformat()
            elif rel == 'index.html' or rel == '404.html':
                want = times[newest].date().isoformat()
            else:
                k = SM.layer_of(rel)
                want = (times[k] if k in times else times[newest]).date().isoformat()
            if last != want:
                out.append('sitemap %s lastmod %s, expected %s' % (rel, last, want))
    readme = os.path.join(root, 'export', 'README.txt')
    if os.path.exists(readme):
        first = open(readme, encoding='utf-8').read().split('\n', 1)[0]
        if fb not in first:
            out.append('export/README.txt says %r, food-bank stamp is %s' % (first, fb))
        for m in FIND.finditer(open(readme, encoding='utf-8').read()):
            if not OK.match(m.group(0)):
                out.append('export/README.txt: %s is not the approved format' % m.group(0))
    return out

def table(root=ROOT):
    """One row per kind of date: where it shows, the time, and which source it follows."""
    raw = json.loads(open(os.path.join(root, 'stamp.js'), encoding='utf-8').read().split('=', 1)[1].rstrip().rstrip(';'))
    layers = raw.get('layers') or {}
    dates = json.load(open(os.path.join(root, 'overrides', 'page_dates.json'), encoding='utf-8'))
    rows = []
    for k, name in (('fb', 'Food banks'), ('sh', 'Shelters'), ('ws', 'Warm spaces')):
        v = layers.get(k) or {}
        rows.append((name + ' refresh', v.get('label', 'missing'), 'stamps/%s.json and stamp.js layers.%s' % (k, k)))
    if raw.get('checked'):
        rows.append(('Phones and opening times checked', raw['checked'].get('label'), 'stamps/checked.json (a finished full_check, not the publish)'))
    newest = max(layers, key=lambda k: london(layers[k]['run'])) if layers else ''
    if newest:
        rows.append(('Newest layer (home header, FAQ map line, 404)', layers[newest]['label'], 'the later of the three layer stamps'))
    for rel, name in (('faq.html', 'FAQ'), ('terms.html', 'Terms'), ('privacy.html', 'Privacy'), ('accessibility.html', 'Accessibility')):
        e = dates.get(rel) or {}
        rows.append((name + ' text last changed', lab(london(e['at'])) if e.get('at') else 'missing', 'overrides/page_dates.json (moves when that page\'s wording changes)'))
    rows.append(('Card checked / closed / scheme date', 'D Mon YYYY from that record', 'the listing\'s own checked_date, closed_on or scheme date'))
    return rows

def main():
    if '--table' in sys.argv:
        for name, when, src in table():
            print('%s | %s | %s' % (name, when, src))
        return
    bad = problems()
    if bad:
        print('date check failed:', file=sys.stderr)
        for x in bad[:40]:
            print('- ' + x, file=sys.stderr)
        if len(bad) > 40:
            print('- ... %d more' % (len(bad) - 40), file=sys.stderr)
        sys.exit(1)
    print('date check ok')

if __name__ == '__main__':
    main()
