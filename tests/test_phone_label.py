"""Optional phone label on list cards and pin pop-ups (food banks, shelters, warm spaces).

Food banks: overrides/phone_labels.json, applied by build.py, kept through compact.py.
Shelters and warm spaces: optional phone_label on the contact override, copied by
shelter_contacts.apply on every refresh. A label never adds or changes a number.
Shown in full (no ellipsis) under the number, in light and dark, on the list card and the pop-up.
"""
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import shelter_contacts as sc

def rd(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()


def _until(page, js, arg=None, timeout=20000):
    """Poll a predicate with page.evaluate. The site's CSP has no 'unsafe-eval', which blocks
    Playwright's string-based function polling; evaluate runs through DevTools and is not blocked."""
    import time
    end = time.time() + timeout / 1000.0
    last = None
    while time.time() < end:
        try:
            last = page.evaluate(js, arg)
        except Exception as e:  # a navigation mid-poll
            last = '%s: %s' % (type(e).__name__, e)
        else:
            if last is True:
                return
        time.sleep(0.25)
    raise AssertionError('timed out waiting for %s (last=%r)' % (js.strip()[:80], last))

class Apply(unittest.TestCase):
    def test_label_with_existing_phone_does_not_change_the_number(self):
        it = [{"id": "a", "phone": "0161 236 7537", "tel": "01612367537"}]
        sc.apply(it, {"a": {"phone_label": "  Central service line  "}})
        self.assertEqual(it[0]["phone"], "0161 236 7537")
        self.assertEqual(it[0]["tel"], "01612367537")
        self.assertEqual(it[0]["phone_label"], "Central service line")

    def test_label_copied_when_a_number_is_filled(self):
        it = [{"id": "a", "phone": ""}, {"id": "b", "phone": "01274 435999", "tel": "01274435999"}]
        sc.apply(it, {"a": {"phone": "0161 236 7537", "phone_label": "Library service line"},
                      "b": {"phone_fix": "01274 481039", "phone_label": "Shared venue line"}})
        self.assertEqual(it[0]["tel"], "01612367537")
        self.assertEqual(it[0]["phone_label"], "Library service line")
        self.assertEqual(it[1]["tel"], "01274481039")
        self.assertEqual(it[1]["phone_label"], "Shared venue line")

    def test_no_label_without_a_phone_and_blank_or_non_string_ignored(self):
        it = [{"id": "a", "phone": ""}, {"id": "b", "phone": "0161 236 7537", "tel": "01612367537"},
              {"id": "c", "phone": "0161 236 7537", "tel": "01612367537", "phone_label": "keep me"}]
        sc.apply(it, {"a": {"phone_label": "Library service line"}, "b": {"phone_label": "   "},
                      "c": {"email": "a@b.c"}})
        self.assertNotIn("phone_label", it[0])
        self.assertEqual(it[0].get("phone"), "")
        self.assertNotIn("phone_label", it[1])
        self.assertEqual(it[2]["phone_label"], "keep me")
        it[1]["phone_label"] = "nope"
        sc.apply([it[1]], {"b": {"phone_label": 12}})
        self.assertEqual(it[1]["phone_label"], "nope")

    def test_dropped_phone_drops_the_label(self):
        it = [{"id": "d", "phone": "0300 123 1966", "tel": "03001231966", "phone_label": "old"}]
        sc.apply(it, {"d": {"drop_phone": True, "phone_label": "Central service line"}})
        self.assertEqual(it[0]["tel"], "")
        self.assertNotIn("phone_label", it[0])

class Wiring(unittest.TestCase):
    def test_sources_show_the_label_on_list_and_popup(self):
        html, layers, css, build = rd("index.html"), rd("layers.js"), rd("v3.css"), rd("scripts/build.py")
        self.assertIn("function phLabText(lab)", html)
        self.assertIn("window.phLab=phLab", html)
        self.assertIn("i.phone_label?phLab(i)", html)
        self.assertIn("${phLab(i)}", html[html.index("function pop"):])
        self.assertIn("phLab(i)", layers)
        self.assertIn("Number for (.+)$", layers)
        self.assertIn("lab.strip()", build)
        self.assertIn("'phone_label'", rd("scripts/compact.py"))
        self.assertIn("p.plab", css)
        self.assertIn("text-overflow:clip", css)
        self.assertIn("white-space:normal", css)
        self.assertNotIn("text-overflow:ellipsis", css[css.index("Optional phone label"):])

LONG = "Shared community venue and the central desk library service line"
MEASURE = """(el, expected) => {
  const s = getComputedStyle(el);
  const er = el.getBoundingClientRect();
  const card = el.closest('.card,.pop') || el.parentElement;
  const cr = card.getBoundingClientRect();
  const m = s.color.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
  let lum = null;
  if (m) { const a = [+m[1], +m[2], +m[3]].map(v => v/255); lum = 0.2126*a[0] + 0.7152*a[1] + 0.0722*a[2]; }
  return {text: el.textContent, color: s.color, lum, whiteSpace: s.whiteSpace, overflow: s.overflow,
    textOverflow: s.textOverflow, lineClamp: s.webkitLineClamp || s.lineClamp || '',
    inButton: !!el.closest('a,button'),
    fits: el.scrollWidth <= el.clientWidth + 2 && el.scrollHeight <= el.clientHeight + 2,
    inside: er.width > 20 && er.height > 8 && er.left >= cr.left - 1 && er.right <= cr.right + 1,
    expected};
}"""

def _check(info, expected, dark_surface):
    assert info["text"] == expected, info
    assert info["fits"] and info["inside"], info
    assert not info["inButton"], info
    assert "nowrap" not in info["whiteSpace"], info
    assert info["textOverflow"] != "ellipsis", info
    assert info["lineClamp"] in ("", "none", "unset"), info
    # dark cards: light text. light cards and the leaflet pop-up: dark text.
    if dark_surface:
        assert info["lum"] is not None and info["lum"] > 0.7, info
    else:
        assert info["lum"] is not None and info["lum"] < 0.25, info

class Render(unittest.TestCase):
    def test_cards_and_popups_keep_the_full_label(self):
        try:
            from playwright.sync_api import sync_playwright
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import newlook_render as R
        except Exception as e:
            raise unittest.SkipTest(str(e))
        with sync_playwright() as pw:
            try:
                b, p = R.open_page(pw, "dark", 390)
            except Exception as e:
                raise unittest.SkipTest("no browser: %s" % e)
            b.close()
            for scheme, width in (("dark", 390), ("dark", 1366), ("light", 390), ("light", 1366)):
                b, p = R.open_page(pw, scheme, width)
                try:
                    self._one(p, scheme, width)
                finally:
                    b.close()

    def _one(self, p, scheme, width):
        light = scheme == "light"
        p.evaluate("on => { document.documentElement.classList.toggle('light', on); }", light)
        # Published food-bank labels (no data rewrite): prefix, and as-written when it ends in line/number.
        for fid, expected in (("west-ardsley", "Number for West Ardsley Friday pantry"), ("amble", "Referral line")):
            card = self._fb_card(p, fid)
            _check(card.evaluate(MEASURE, expected), expected, dark_surface=not light)
            pop = self._fb_popup(p, fid, width)
            # Leaflet pop-up is a light card in both themes; the phone sheet follows the theme.
            popup_dark = (not light) and width < 600
            _check(pop.evaluate(MEASURE, expected), expected, dark_surface=popup_dark)
        # Long label injected in memory only, so a refresh has nothing new to publish.
        card = self._fb_card(p, "amble", LONG)
        _check(card.evaluate(MEASURE, LONG), LONG, dark_surface=not light)
        pop = self._fb_popup(p, "amble", width)
        _check(pop.evaluate(MEASURE, LONG), LONG, dark_surface=(not light) and width < 600)
        if width < 600:
            self.assertGreater(card.evaluate("el => el.getBoundingClientRect().height"), 28)  # narrow card: wraps, not clipped to one line
        for layer, lab in (("sh", "Central service line"), ("ws", "Shared venue line")):
            p.click("#v3big [data-l=%s]" % layer)
            var = "SHELTERS" if layer == "sh" else "WARMSPACES"
            _until(p, "v => !!(window[v] && window[v].items && window[v].items.length > 10)", var, 20000)
            p.wait_for_timeout(400)
            sel = "#xlist .card.x%s .plab" % layer
            p.evaluate("""([v, lab]) => {
              window[v].items.forEach(i => { if (i.tel || i.phone) i.phone_label = lab; });
              const i = window[v].items.find(x => (x.tel || x.phone) && x.lat != null);
              nearest(i.lat, i.lng, i.postcode || i.name);
            }""", [var, lab])
            p.wait_for_selector(sel, timeout=10000)
            el = p.query_selector(sel)
            _check(el.evaluate(MEASURE, lab), lab, dark_surface=not light)
            # Pin pop-up for shelters and warm spaces is the bottom sheet.
            opened = p.evaluate("""() => {
              let hit = null;
              map.eachLayer(layer => { if (hit || !layer.eachLayer) return;
                layer.eachLayer(m => { if (hit) return;
                  const cn = m.options && m.options.icon && m.options.icon.options && m.options.icon.options.className || '';
                  if (String(cn).indexOf('xpin') >= 0) hit = m; }); });
              if (!hit) return false; hit.fire('click'); return true;
            }""")
            self.assertTrue(opened, layer)
            p.wait_for_selector("#sheet.open .plab", timeout=5000)
            sheet = p.query_selector("#sheet.open .plab")
            _check(sheet.evaluate(MEASURE, lab), lab, dark_surface=not light)
            p.keyboard.press("Escape")
            p.wait_for_timeout(200)

    def _fb_card(self, p, fid, label=None):
        if label:
            p.evaluate("""([id, lab]) => { const i = items.find(x => x.id === id); i.phone_label = lab; }""", [fid, label])
        ok = p.evaluate("""id => { const i = items.find(x => x.id === id); if (!i) return false;
          nearest(i.lat, i.lng, i.postcode || i.name); return true; }""", fid)
        self.assertTrue(ok, fid)
        p.wait_for_timeout(400)
        h = p.evaluate_handle("""id => { const i = items.find(x => x.id === id);
          return [...document.querySelectorAll('#list .card')].find(c => (c.querySelector('h3')||{}).textContent === i.name) || null; }""", fid)
        card = h.as_element()
        self.assertIsNotNone(card, fid)
        el = card.query_selector(".plab")
        self.assertIsNotNone(el, fid)
        return el

    def _fb_popup(self, p, fid, width):
        p.evaluate("""id => { const k = items.findIndex(x => x.id === id); select(k, false); }""", fid)
        sel = "#sheet.open .plab" if width < 600 else "#map .leaflet-popup-content .plab"
        _until(p, """sel => document.querySelectorAll(sel).length === 1""", sel, 5000)
        el = p.query_selector(sel)
        self.assertIsNotNone(el, fid)
        return el

if __name__ == "__main__":
    unittest.main()
