"""Shared preview/screenshot helper: ALWAYS renders through the real index.html + v3.css + data.js
(served from this checkout via Playwright routing), with cards shown in #list exactly as live does.
Never render standalone cards. Usage: python3 tests/newlook_render.py OUTDIR id1 id2 ..."""
import mimetypes, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import check_browser as B
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = 'https://fyfb.local/'
CHROME = next((p for p in ('/usr/bin/google-chrome', '/usr/bin/chromium') if os.path.exists(p)), None)

def _serve(route):
    url = route.request.url
    if not url.startswith(HOST): return route.abort()  # no tiles/analytics: deterministic, offline
    path = os.path.join(ROOT, url[len(HOST):].split('?')[0].split('#')[0] or 'index.html')
    if not os.path.isfile(path): return route.fulfill(status=404, body='')
    route.fulfill(status=200, body=open(path, 'rb').read(), content_type=mimetypes.guess_type(path)[0] or 'application/octet-stream')

def open_page(pw, scheme='dark', width=390, base=None):
    b = pw.chromium.launch(**({'executable_path': CHROME} if CHROME else {}))
    ctx = b.new_context(viewport={'width': width, 'height': 844}, device_scale_factor=2, color_scheme=scheme, service_workers='block')
    p = ctx.new_page()
    if base is None: p.route('**/*', _serve); base = HOST + 'index.html'
    B.stub_map_tiles(p)  # after the catch-all, which aborts anything that is not this checkout
    p.goto(base + '?fresh=1', wait_until='load'); p.wait_for_function('()=>{try{return items.length>1000}catch(e){return false}}', timeout=60000)
    p.wait_for_timeout(800)
    return b, p

def show_in_list(p, fid):
    """List the cards nearest the food bank (as a postcode search does) and return its card in #list."""
    ok = p.evaluate("""id=>{const i=items.find(x=>x.id===id);if(!i)return false;nearest(i.lat,i.lng,i.postcode||i.name);return true}""", fid)
    assert ok, fid
    p.wait_for_timeout(700)
    h = p.evaluate_handle("""id=>{const i=items.find(x=>x.id===id);return [...document.querySelectorAll('#list .card')].find(c=>(c.querySelector('h3')||{}).textContent===i.name)||null}""", fid)
    return h.as_element()

def card_style(card):
    return card.evaluate("""c=>{const a=c.querySelector('a.btn.call:not(.xfbk)'),f=c.querySelector('a.btn.call.xfbk'),cs=e=>e&&getComputedStyle(e);
      const ic=a&&a.querySelector('svg.ico');return {call:a?a.textContent.trim():null,call_bg:a?cs(a).backgroundColor:null,call_fs:a?cs(a.querySelector('*:not(svg):not(path)')||a).fontSize:null,
      icon:ic?cs(ic).fill:null,fb:f?f.textContent.trim():null,fb_bg:f?cs(f).backgroundColor:null,
      psrc:(c.querySelector('.psrc')||{}).textContent||null,mb:cs(c).marginBottom}}""")

if __name__ == '__main__':
    from playwright.sync_api import sync_playwright
    out, ids = sys.argv[1], sys.argv[2:]
    base = os.environ.get('BASE')  # e.g. https://helpmap.uk/ to shoot live through the same path
    tag = os.environ.get('TAG', 'branch')
    with sync_playwright() as pw:
        for scheme in ('light', 'dark'):
            b, p = open_page(pw, scheme, base=base)
            for fid in ids:
                c = show_in_list(p, fid); assert c, fid
                c.scroll_into_view_if_needed(); print(tag, scheme, fid, card_style(c))
                c.screenshot(path=os.path.join(out, '%s_%s_390_%s.png' % (tag, fid.replace('/', '_'), scheme)))
            b.close()
