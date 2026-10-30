"""Dean hand-verified shelters (30 Oct 2026): four manual entries and eight sweep exclusions."""
import json, os, re

ROOT = os.path.join(os.path.dirname(__file__), "..")
OV = os.path.join(ROOT, "overrides")

NEW_IDS = (
    "man-hastings-wuth-night-shelter",
    "man-mary-rose-court-basingstoke",
    "man-ymca-basingstoke",
    "man-ymca-watford-charter",
)
EXCLUDE = (
    ("CT17 9BZ", "Victory House"),
    ("TN34 1EA", "who a) have been verified rough sleeping"),
    ("TN34 3UY", "451100"),
    ("SM4 5DX", "Merton Civic Centre"),
    ("S1 2PF", "Victoria Hall Methodist Church"),
    ("M27 5AW", "Salford Housing Options"),
    ("WV1 4BL", "(freephone"),
    ("AL1 5UG", "Vineyard Church"),
)
SWEEP_JUNK = re.compile(
    r"Victory House \(CT17|who a\) have been verified|451100 \(TN34|Merton Housing Advice|"
    r"Victoria Hall Methodist|Salford|M27 5AW|\(freephone|Mary Rose Court \(RG21|Eastrop Way \(RG21|"
    r"Vineyard Church \(AL1|YMCA Watford Charter",
    re.I,
)


def _manual():
    return {x["id"]: x for x in json.load(open(os.path.join(OV, "shelters_manual.json"), encoding="utf-8"))}


def test_manual_shelters_on_allowlist():
    manual = _manual()
    verified = json.load(open(os.path.join(OV, "shelters_verified.json"), encoding="utf-8"))
    for i in NEW_IDS:
        m = manual[i]
        v = verified[i]
        assert m["source"] == "Manual (verified from source pages)"
        assert m["last_verified"] == "2026-10-30"
        assert m["flag_closed"] is False and m["stale"] is False
        assert m["access_type"] == "referral_only"
        assert v["verified_on"] == "2026-10-30"
        assert v["access_type"] == "referral_only"
        assert v.get("evidence_url") and (v.get("quote") or v.get("day_time_quote"))


def test_hastings_and_basingstoke_details():
    h = _manual()["man-hastings-wuth-night-shelter"]
    assert h["postcode"] == "TN34 1EA" and h["phone"] == "07367 060708"
    assert h["season"] == "Until 30 Nov 2026"
    assert "last entry 10pm" in h["hours"]
    y = _manual()["man-ymca-basingstoke"]
    assert y["groups"] == ["Young people"] and y["beds"] == "80"


def test_phone_baseline_venue_lines_only():
    pb = json.load(open(os.path.join(OV, "phone_baseline.json"), encoding="utf-8"))["listings"]
    expect = {
        "man-hastings-wuth-night-shelter": ("07367 060708", "07367060708"),
        "man-mary-rose-court-basingstoke": ("01256 472233", "01256472233"),
        "man-ymca-basingstoke": ("01256 479696", "01256479696"),
        "man-ymca-watford-charter": ("01923 353600", "01923353600"),
    }
    for i, (phone, tel) in expect.items():
        row = pb[i]
        assert row["layer"] == "shelters"
        assert row["phone"] == phone and row["tel"] == tel
        assert "council" not in row


def test_sweep_exclusions():
    rows = json.load(open(os.path.join(OV, "sweep_exclude.json"), encoding="utf-8"))
    by_pc = {(r["postcode"].replace(" ", "").upper(), r["name"]): r for r in rows}
    reason = "Dean 30 Oct 2026 hand check: not a place to stay"
    for pc, name in EXCLUDE:
        key = (pc.replace(" ", "").upper(), name)
        assert key in by_pc, key
        assert by_pc[key]["reason"] == reason


def test_pending_dean_sweep_section_cleared():
    md = open(os.path.join(ROOT, "reports", "pending_dean.md"), encoding="utf-8").read()
    block = md.split("<!-- /sweep shelters -->", 1)[0].split("Shelter candidates from the sweep", 1)[-1]
    assert "- none" in block
    assert not SWEEP_JUNK.search(block)
