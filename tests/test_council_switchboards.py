"""Dean's rule: a council's general switchboard / contact-centre number is never a venue's
direct line or out-of-hours line (shelters and warm spaces). Locked lines are kept."""
import copy, json, os, sys
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import council_switchboard as cs
import phone_lock
import shelter_contacts

# The 16 warm spaces a contacts re-run over main's file gave a council switchboard (13 numbers).
BLOCKED = {
    "ww-64379621": "01279 655261", "ww-58212607": "020 7527 2000", "ww-65437525": "01259 450000",
    "evergreen-elderberries-welling": "020 8303 7171", "ww-55473505": "0300 131 2131",
    "ww-57993936": "01702 215000", "swk-london-lgbtq-community-centre": "020 7525 5000",
    "ww-68472828": "01827 715341", "ww-55475831": "0300 131 2131", "ww-55474480": "01752 668000",
    "ww-65413950": "01789 267575", "ww-60625347": "0300 131 2131", "ww-57951953": "020 8496 3000",
    "ww-67526400": "01305 221000", "ww-55474116": "01702 215000", "ww-59974983": "020 8379 1000",
}
LOCKED = {"ww-57953124": "0300 456 3554", "ww-65437367": "0300 456 3554"}  # Ceredigion, Dean-approved

def items(name):
    s = open(os.path.join(ROOT, name), encoding="utf-8").read()
    return json.loads(s[s.index("{"):s.rindex("}") + 1])["items"]

def entry(num, label="Council out-of-hours homeless line"):
    return {"council": "X Council", "council_phone": num, "council_ooh": num, "council_label": label, "council_url": "https://x.gov.uk/contact-us"}

def test_every_blocked_number_is_a_known_switchboard():
    for n in set(BLOCKED.values()):
        assert cs.is_general(n), n
        assert cs.is_general("+44 " + n[1:]), n  # any formatting
    for n in LOCKED.values():
        assert cs.is_locked(n) and not cs.is_general(n)

def test_contacts_step_never_assigns_switchboards():
    data = {i: entry(n) for i, n in BLOCKED.items()}
    data.update({i: entry(n, "Social services out-of-hours team (emergency housing)") for i, n in LOCKED.items()})
    its = [{"id": i, "name": i} for i in data]
    shelter_contacts.apply(its, data)
    for x in its:
        if x["id"] in BLOCKED:
            assert not any(k.startswith("council") for k in x), x
        else:
            assert x["council_phone"] == x["council_ooh"] == LOCKED[x["id"]]

def test_area_council_switchboard_and_feed_number_rejected():
    data = {"_councils": {"wf": entry("020 8496 3000")}, "a": {"area": "wf"}, "b": {"phone": "01702 215000"}}
    its = [{"id": "a"}, {"id": "b"}, {"id": "c", **entry("0300 131 2131")}]
    data["c"] = {"email": "x@y.org"}
    shelter_contacts.apply(its, data)
    for x in its:
        assert not x.get("council_phone") and not x.get("council_ooh")
    assert not its[1].get("phone")  # never as a venue's direct line either

def test_settle_and_guard_drop_switchboard_and_keep_locked(tmp_path):
    os.makedirs(tmp_path / "overrides")
    base = {"listings": {"sw": {"layer": "warmspaces", **{k: v for k, v in entry("020 7527 2000").items() if k in phone_lock.FIELDS}},
                         "ok": {"layer": "warmspaces", **{k: v for k, v in entry("0300 456 3554").items() if k in phone_lock.FIELDS}}}}
    (tmp_path / "overrides" / "phone_baseline.json").write_text(json.dumps(base))
    its = [{"id": "sw", **entry("020 7527 2000")}, {"id": "ok", **entry("0300 456 3554")}, {"id": "sw2"}]
    for x in its: phone_lock.settle_council(x)
    phone_lock.guard(its, str(tmp_path), via="refresh", layer="warmspaces")
    assert not its[0].get("council_phone") and not its[0].get("council_ooh")
    assert its[1]["council_phone"] == "0300 456 3554"
    its2 = [{"id": "sw"}]  # a refresh with the field missing must not restore the frozen switchboard
    phone_lock.guard(its2, str(tmp_path), via="refresh", layer="warmspaces")
    assert not its2[0].get("council_phone")

def test_nightly_refresh_over_published_files_adds_none():
    """Re-running the contacts step (as refresh-warmspaces / build_shelters do) adds no switchboard."""
    for lay, path in (("warmspaces.js", shelter_contacts.WS), ("shelters.js", shelter_contacts.PATH)):
        its = copy.deepcopy(items(lay))
        shelter_contacts.apply(its, shelter_contacts.load(path))
        for x in its: phone_lock.settle_council(x)
        phone_lock.guard(its, phone_lock.ROOT, via="refresh", layer=lay)
        bad = [(x["id"], x.get("council_phone") or x.get("council_ooh")) for x in its
               if cs.is_general(x.get("council_phone")) or cs.is_general(x.get("council_ooh"))]
        assert not bad, bad
        got = {x["id"]: x for x in its}
        for i, n in LOCKED.items():
            if i in got: assert got[i]["council_phone"] == n

def test_published_and_override_files_hold_no_switchboard():
    for name in ("warmspaces.js", "shelters.js"):
        for x in items(name):
            assert not cs.is_general(x.get("council_phone")) and not cs.is_general(x.get("council_ooh")), x["id"]
            if x["id"] in LOCKED: assert x["council_phone"] == LOCKED[x["id"]]
    for f in ("warmspaces_contacts.json", "shelters_contacts.json"):
        d = json.load(open(os.path.join(ROOT, "overrides", f), encoding="utf-8"))
        for k, v in list(d.items()) + list(d.get("_councils", {}).items()):
            if isinstance(v, dict): assert not cs.strip(dict(v)), (f, k)
    for k, v in phone_lock.load()["listings"].items():
        assert not cs.strip(dict(v)), k
