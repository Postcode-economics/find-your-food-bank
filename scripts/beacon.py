"""Cloudflare Web Analytics beacon for helpmap.uk (token from Dean, 25 Oct 2026), on every generated page.
Skipped for our own automated checks (webdriver/headless, ?nocount, localStorage nocount=1). build_seo.py emits it in
every area page and 404.html; seo_meta.py (runs in every workflow) makes sure every HTML page in the site carries it."""
import glob, os
TOKEN = '6a7058ad322d49b481a8849a493add24'
SNIPPET = '<script>/* Analytics beacon, skipped for our own automated checks (webdriver/headless, ?nocount, or localStorage nocount=1) - 25 Oct 2026 */(function(){try{var q=location.search,ua=navigator.userAgent||\'\';if(navigator.webdriver||/HeadlessChrome|helpmap-check/i.test(ua)||/[?&]nocount\\b/.test(q)||localStorage.getItem(\'nocount\')===\'1\'){if(/[?&]nocount\\b/.test(q))localStorage.setItem(\'nocount\',\'1\');return}var s=document.createElement(\'script\');s.defer=true;s.src=\'https://static.cloudflareinsights.com/beacon.min.js\';s.setAttribute(\'data-cf-beacon\',\'{"token": "6a7058ad322d49b481a8849a493add24"}\');document.head.appendChild(s)}catch(_){}})();</script>'
def inject(text):
    if 'data-cf-beacon' in text or '</body>' not in text: return text
    return text.replace('</body>', SNIPPET + '</body>', 1)
def pages(root):
    out = []
    for p in glob.glob(os.path.join(root, '*.html')) + glob.glob(os.path.join(root, '*', '**', '*.html'), recursive=True):
        rel = os.path.relpath(p, root).replace(os.sep, '/')
        if rel.split('/')[0] in ('index.html', '404.html', 'faq.html', 'terms.html', 'privacy.html', 'accessibility.html', 'food-banks', 'warm-spaces', 'shelters'): out.append(p)
    return sorted(out)
def inject_all(root):
    n = 0
    for p in pages(root):
        t = open(p, encoding='utf-8').read(); t2 = inject(t)
        if t2 != t: open(p, 'w', encoding='utf-8').write(t2); n += 1
    return n
