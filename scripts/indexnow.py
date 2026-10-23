"""Tell search engines (IndexNow: Bing, Yandex, Seznam, Naver...) which public pages changed in this run. Fail-safe: never fails the job.
Usage: python scripts/indexnow.py <base-commit>   (compares <base-commit> with HEAD)
Only real content changes count: the per-run timestamps (dateModified, 'Map data last checked', 'Updated', ?v=r...) are ignored,
so unchanged pages are not pinged every run."""
import glob, json, os, re, subprocess, sys, urllib.request
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
HOST = 'helpmap.uk'
NOISE = [r'<script type="application/ld\+json" data-ld="[a-z]+">.*?</script>', r'<!--mapchk(?:-cy|js)?-->.*?<!--/mapchk(?:js)?-->',
         r'Information last updated [^.<]*\.', r'\?v=r\d{8}T\d{4}', r'<a id="freshtxt"[^>]*>[^<]*</a>']

def key(root=ROOT):
    ks = [os.path.basename(p)[:-4] for p in glob.glob(os.path.join(root, '*.txt')) if re.fullmatch(r'[0-9a-f]{32}', os.path.basename(p)[:-4])]
    return ks[0] if ks else None

def norm(s):
    for p in NOISE: s = re.sub(p, '', s, flags=re.S)
    return s

def url_of(rel):
    if rel == 'index.html': return 'https://%s/' % HOST
    if rel.endswith('/index.html'): return 'https://%s/%s' % (HOST, rel[:-len('index.html')])
    return 'https://%s/%s' % (HOST, rel)

def public(rel):
    return rel in ('index.html', 'faq.html', 'terms.html', 'privacy.html', 'accessibility.html') or \
        (rel.endswith('/index.html') and rel.split('/')[0] in ('food-banks', 'warm-spaces', 'shelters'))

def changed(base, root=ROOT):
    git = lambda *a: subprocess.run(['git', '-C', root] + list(a), capture_output=True, text=True)
    names = git('diff', '--name-only', base, 'HEAD').stdout.split()
    out = []
    for rel in names:
        if not public(rel): continue
        p = os.path.join(root, rel)
        new = open(p, encoding='utf-8').read() if os.path.exists(p) else None
        old = git('show', '%s:%s' % (base, rel)); old = old.stdout if old.returncode == 0 else None
        if new is None or old is None or norm(new) != norm(old): out.append(url_of(rel))   # added, removed or really changed
    return sorted(set(out))

def ping(urls, k):
    body = json.dumps({'host': HOST, 'key': k, 'keyLocation': 'https://%s/%s.txt' % (HOST, k), 'urlList': urls[:10000]}).encode()
    r = urllib.request.Request('https://api.indexnow.org/indexnow', data=body, headers={'Content-Type': 'application/json; charset=utf-8'})
    with urllib.request.urlopen(r, timeout=30) as resp: return resp.status

def main():
    try:
        k = key()
        if not k: print('indexnow: no key file, skipped'); return
        urls = changed(sys.argv[1] if len(sys.argv) > 1 else 'HEAD~1')
        if not urls: print('indexnow: no changed pages'); return
        print('indexnow: %d changed pages, HTTP %s' % (len(urls), ping(urls, k)))
    except Exception as e:
        print('::warning::indexnow ping failed (ignored): %s' % e)

if __name__ == '__main__':
    main()
