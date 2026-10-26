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
    return v
if __name__ == '__main__': print('build version', sync())
