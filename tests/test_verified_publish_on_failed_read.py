import json, os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import common

def _run(rc_entry, vid="man-ss-belvidere-family-centre"):
    v = {vid: {"evidence_url": "https://e.x/", "quote": "q", "verified_on": "2026-11-02", "phone": "0151 329 0307"}}
    fresh = [{"id": vid, "name": "B"}]
    d = tempfile.mkdtemp(); pend = os.path.join(d, "shelters_pending.json"); os.makedirs(os.path.join(d, "logs"), exist_ok=True); os.makedirs(os.path.join(d, "reports"), exist_ok=True); cwd = os.getcwd(); os.chdir(d)
    import recheck
    orig = recheck.recheck_all
    recheck.recheck_all = lambda *a, **k: {vid: rc_entry}
    try:
        out = common.verification_gate(fresh, {"items": []}, v, "2026-11-03", pend)
    finally:
        recheck.recheck_all = orig; os.chdir(cwd)
    return out[0] if isinstance(out, tuple) else out

def test_verified_approved_publishes_on_403():
    pub = _run({"ok": False, "http": 403, "reason": "source unreachable this run (HTTP 403)"})
    assert [x["id"] for x in pub] == ["man-ss-belvidere-family-centre"]
    assert pub[0]["verified_fallback"] and pub[0]["phone"] == "0151 329 0307"

def test_closed_source_still_dropped():
    pub = _run({"ok": False, "reason": "source says closed"}) if "source says closed" in common.CLOSED_REASONS else _run({"ok": False, "reason": list(common.CLOSED_REASONS)[0]})
    assert pub == []

def test_unapproved_still_held():
    pub = _run({"ok": False, "http": 403, "reason": "x"}, vid="not-approved-id")
    assert pub == []
