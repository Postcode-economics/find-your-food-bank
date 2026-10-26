"""Single source for the build version (25 Oct 2026): the service worker cache name in sw.js (const C='fyfb-vNN').
version.json and index.html (<meta name="helpmap-build"> + the self-heal check) are written from it, so a sw bump never
needs hand edits. Called by seo_meta.py (runs in every refresh/sweep workflow) and runnable on its own."""
import json, os, re
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
def sync(root=ROOT):
    v = re.search(r"const C='([^']+)'", open(os.path.join(root, 'sw.js'), encoding='utf-8').read()).group(1)
    vp = os.path.join(root, 'version.json'); new = json.dumps({'build': v})
    if not os.path.exists(vp) or open(vp).read() != new: open(vp, 'w').write(new)
    ip = os.path.join(root, 'index.html'); h = open(ip, encoding='utf-8').read()
    h2 = re.sub(r'(<meta name="helpmap-build" content=")[^"]*(")', r'\g<1>%s\g<2>' % v, h)
    h2 = re.sub(r"(var b=')[^']*(',k='hmHeal')", r"\g<1>%s\g<2>" % v, h2)
    if h2 != h: open(ip, 'w', encoding='utf-8').write(h2)
    sync_precache(root, h2)
    return v
def wanted_versioned(html):
    """Every local ?v= asset index.html loads (css + js). The SW precache must list exactly these (25 Oct 2026: SHELL drifted)."""
    # data files (?v= changes every refresh) are network-first in sw.js and never precached by version: skip them
    return sorted(x for x in set(re.findall(r'(?:href|src)="((?!https?:|//)[\w./-]+\.(?:js|css)\?v=[\w.-]+)"', html)) if not re.match(r'(data|stamp|access|shelters|warmspaces)\.js', x))
def sync_precache(root=ROOT, html=None):
    html = html or open(os.path.join(root, 'index.html'), encoding='utf-8').read()
    sp = os.path.join(root, 'sw.js'); s = open(sp, encoding='utf-8').read()
    m = re.search(r"SHELL=\[([^\]]*)\]", s); items = re.findall(r"'([^']*)'", m.group(1))
    keep = [x for x in items if '?v=' not in x]; want = wanted_versioned(html)
    new = keep[:]
    for w in want:   # put each versioned entry right after its plain file, else at the end
        b = w.split('?')[0]; new.insert(new.index(b) + 1 if b in new else len(new), w)
    s2 = s[:m.start(1)] + ','.join("'%s'" % x for x in new) + s[m.end(1):]
    if s2 != s: open(sp, 'w', encoding='utf-8').write(s2)
    return new
if __name__ == '__main__': print('build version', sync())
