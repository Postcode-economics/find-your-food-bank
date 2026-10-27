"""Read-only privacy check: Dean's private address/phone must not appear on helpmap.uk.

Reads PRIVATE_BLOCKLIST from the environment (one entry per line, or separated by |).
Scans every listing in export/*.json and every public file in the site (all pages,
data files, feeds), and optionally the live pages and feeds on helpmap.uk.

Prints ONLY counts. Never prints, logs or writes a secret value, a matching listing,
or a matching file name. Exits 1 on any match, 2 if the secret is empty/unusable.
Writes nothing.
"""
import json, os, re, sys, urllib.request

SKIP_DIRS = {'.git', '.github', 'tests', 'scripts', 'node_modules', '__pycache__', 'vendor'}
TEXT_EXT = {'.html', '.js', '.json', '.csv', '.txt', '.md', '.xml', '.webmanifest', '.css'}
EXPORTS = ['export/foodbanks.json', 'export/shelters.json', 'export/warmspaces.json']
LIVE = 'https://helpmap.uk'


def entries(raw):
    return [p.strip() for p in re.split(r'[\n|]', raw or '') if p.strip()]


def _digits(s):
    return re.sub(r'\D', '', s or '')


def _phone_forms(digits):
    """National and +44 / 0044 forms of a UK number, as digit strings."""
    if digits.startswith('0044'):
        digits = '0' + digits[4:]
    elif digits.startswith('44') and len(digits) >= 12:
        digits = '0' + digits[2:]
    forms = {digits}
    if digits.startswith('0'):
        forms |= {'44' + digits[1:], '0044' + digits[1:]}
    return forms


def _squash(s):
    return re.sub(r'[^0-9a-z]', '', (s or '').casefold())


def _spaced(s):
    return re.sub(r'\s+', ' ', (s or '').casefold()).strip()


def compile_needles(raw):
    phones, texts = [], []
    for e in entries(raw):
        d = _digits(e)
        has_letters = bool(re.search(r'[a-zA-Z]', e))
        if len(d) >= 10 and not has_letters:
            phones.append(_phone_forms(d))
        elif len(_squash(e)) >= 8:
            texts.append((_spaced(e), _squash(e)))
    return phones, texts


def text_matches(text, needles):
    phones, texts = needles
    if not text:
        return False
    # Digit runs separated only by spaces, dots, dashes, brackets, + count as one number.
    runs = [_digits(m) for m in re.findall(r'[\d+][\d\s().\-+]{8,}\d', text)]
    alld = _digits(text)
    for forms in phones:
        for f in forms:
            if f in alld or any(f in r for r in runs):
                return True
    spaced, squashed = _spaced(text), _squash(text)
    for sp, sq in texts:
        if sp in spaced or sq in squashed:
            return True
    return False


def listing_text(item):
    out = []
    def walk(v):
        if isinstance(v, dict):
            for x in v.values(): walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v: walk(x)
        elif v is not None:
            out.append(str(v))
    walk(item)
    return '\n'.join(out)


def public_files(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            if os.path.splitext(f)[1].lower() in TEXT_EXT:
                yield os.path.join(d, f)


def scan_local(root, needles):
    listings = pages = files = matches = 0
    for rel in EXPORTS:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            continue
        for item in json.load(open(p, encoding='utf-8')).get('items', []):
            listings += 1
            if text_matches(listing_text(item), needles):
                matches += 1
    for p in public_files(root):
        files += 1
        if p.endswith('.html'):
            pages += 1
        try:
            t = open(p, encoding='utf-8', errors='ignore').read()
        except OSError:
            continue
        if text_matches(t, needles):
            matches += 1
    return listings, pages, files, matches


def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'helpmap-privacy-check'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'ignore')


def scan_live(needles, base=LIVE):
    urls = {base + '/'}
    try:
        urls |= set(re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', _get(base + '/sitemap.xml')))
    except Exception:
        pass
    for f in ['data.js', 'data.full.js', 'shelters.js', 'warmspaces.js'] + EXPORTS:
        urls.add(base + '/' + f)
    fetched = failed = matches = 0
    for u in sorted(urls):
        try:
            t = _get(u)
        except Exception:
            failed += 1
            continue
        fetched += 1
        if text_matches(t, needles):
            matches += 1
    return fetched, failed, matches


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    needles = compile_needles(os.environ.get('PRIVATE_BLOCKLIST', ''))
    if not (needles[0] or needles[1]):
        print('PRIVATE_BLOCKLIST is empty or has no usable entries: FAIL')
        return 2
    print(f'blocklist entries loaded: {len(needles[0]) + len(needles[1])}')
    root = '.'
    listings, pages, files, m = scan_local(root, needles)
    print(f'listings checked: {listings}')
    print(f'pages checked: {pages}')
    print(f'public files checked: {files}')
    total = m
    if '--live' in argv:
        fetched, failed, lm = scan_live(needles)
        print(f'live urls fetched: {fetched} (failed: {failed})')
        total += lm
        if failed:
            print('some live urls could not be fetched: FAIL')
            print(f'matches: {total}')
            return 1
    print(f'matches: {total}')
    if total:
        print('RESULT: FAIL - private details found (values not shown)')
        return 1
    print('RESULT: PASS - no private details found')
    return 0


if __name__ == '__main__':
    sys.exit(main())
