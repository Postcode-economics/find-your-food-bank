"""The 36 Street Support shelters link to the organisation's own site; Street Support is credited separately (Dean, 3 Nov 2026)."""
import json, os, re, shutil, subprocess, pytest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _ss():
    d = json.load(open(os.path.join(ROOT, "overrides", "shelters_manual.json")))
    return [e for e in d if e["id"].startswith("man-ss")]

def test_36_entries_own_site_and_credit():
    ss = _ss()
    assert len(ss) == 36
    for e in ss:
        assert e["source_url"].startswith("http") and "streetsupport.net" not in e["source_url"], e["id"]
        assert e["source"] != "Street Support", e["id"]
        assert e["discovery_label"] == "Street Support", e["id"]
        assert e["discovery_url"].startswith("https://www.streetsupport.net/find-help"), e["id"]

def test_card_renders_found_via_credit():
    node = shutil.which("node")
    if not node: pytest.skip("node not installed")
    src = open(os.path.join(ROOT, "layers.js")).read()
    fn = re.search(r"function shSource\(i\)\{.*?</p>`\}", src, re.S).group(0)
    e = _ss()[0]
    js = ("const esc=s=>String(s);const fmt=s=>s;const T={en:{src:'Source',ver:'checked',chk:'c',lst:'l',seen:'s'},cy:{src:'Ffynhonnell',ver:'v',chk:'c',lst:'l',seen:'s'}};"
          + fn + ";console.log(shSource(" + json.dumps(e) + "))")
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout
    assert "Found via" in out and e["discovery_url"] in out and ">Street Support</a>" in out
    assert 'href="%s"' % e["source_url"] in out
