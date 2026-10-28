"""Locks the warm spaces audit fixes (27 Oct 2026, Bot 3 audit; each source fetched twice >60 s apart).
Fixes live in overrides (re-applied every refresh), and the built file must agree."""
import json, os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def J(p): return json.load(open(os.path.join(ROOT, p)))
def items():
    s = open(os.path.join(ROOT, "warmspaces.js")).read()
    return {x["id"]: x for x in json.loads(s[s.index("{"):s.rindex("}") + 1])["items"]}
ADDR = {
    "ww-68911571": "Former scout hall, Chesterfield, Derbyshire S41 0LY",
    "ww-55474670": "Market Place, Kingston upon Thames, Surrey KT1 1JP",
    "ww-65437345": "Springwell Centre, Doncaster, DN12 4AB",
    "ww-68524251": "Baildon Methodist Church, Newton Way, Baildon, Shipley, West Yorkshire BD17 5NH",
    "ww-65420068": "All Saints Room, under St John the Evangelist Church (access from Pevensey Road), St Leonards-on-Sea, East Sussex TN38 0LF",
}
def test_address_overrides():
    fx = {f["id"]: f for f in J("overrides/warmspaces_fixes.json")}
    for i, a in ADDR.items():
        assert fx[i]["address"] == a and fx[i].get("reason")
        assert "lat" not in fx[i] and "lng" not in fx[i]  # postcodes unchanged, pins unchanged
        assert fx[i]["postcode"] in a
def test_stretham_fortnightly():
    v = J("overrides/warmspaces_verified.json")["ww-63065216"]
    assert v["hours"] == {"Thu": "14:00 - 16:00 Fortnightly"} and "fortnightly" in v["day_time_quote"]
def test_built_file_matches():
    it = items()
    for i, a in ADDR.items():
        if i in it: assert it[i]["address"] == a
    if "ww-63065216" in it: assert it["ww-63065216"]["hours"] == {"Thu": "14:00 - 16:00 Fortnightly"}

# Bot 4 audit additions (27 Oct 2026)
def test_bot4_fixes():
    fx = {f["id"]: f for f in J("overrides/warmspaces_fixes.json")}
    assert fx["ww-55472884"]["address"] == "Abbey Community Centre, 172 Belsize Road, London NW6 4BJ"
    v = J("overrides/warmspaces_verified.json")
    assert v["ww-64379462"]["hours"] == {"Mon": "10:00 - 13:00 / 14:00 - 17:00", "Wed": "10:00 - 13:00 / 14:00 - 17:00", "Thu": "10:00 - 13:00 / 14:00 - 17:00", "Sat": "10:00 - 13:00"}
    assert v["ww-68896770"]["hours"]["Fri"] == "11:00 - 15:00"
    u = J("overrides/warmspaces_unverified.json")
    assert u["ww-55473520"]["phone"] == "01606 42943"
    for i in ("ww-55473766", "ww-65420022", "ww-69210060", "ww-57952336"):
        assert u[i]["call_check"] is True and u[i]["flag"] and u[i]["sign_url"]
    it = items()
    for i in ("ww-55473766", "ww-65420022", "ww-69210060", "ww-57952336"):
        if i in it: assert it[i].get("call_check") is True

# Bot 4 browser batch 1 (28 Oct 2026)
def test_bot4_browser_batch1():
    fx = {f["id"]: f for f in J("overrides/warmspaces_fixes.json")}
    assert "17 Churchgate" in fx["ww-65438881"]["address"] and "Lockleaze" in fx["ww-65438865"]["address"]
    assert "2 Station Grove" in fx["ww-65070433"]["address"] and "Highcroft Avenue" in fx["ww-59806670"]["address"]
    assert fx["ww-65441837"]["address"].startswith("Units 5 & 6")
    u = J("overrides/warmspaces_unverified.json")
    assert u["ww-65438881"]["phone"] == "01623 677 200"
    for i in ("ww-67506955", "ww-55475166", "sbadc-the-hub-south-brent", "ww-66561578", "ww-69211163", "ww-57952419", "ww-69155575", "ww-68917333"):
        assert u[i]["call_check"] is True and u[i]["flag"] and u[i]["sign_url"]

# Bot 4 browser batch 2 (28 Oct 2026)
def test_bot4_browser_batch2():
    fx = {f["id"]: f for f in J("overrides/warmspaces_fixes.json")}
    assert fx["ww-67526400"]["address"].startswith("22B Butts Pond") and "24 Regent Terrace" in fx["ww-65420071"]["address"]
    assert "London Road, Morden" in fx["ww-55475350"]["address"]
    u = J("overrides/warmspaces_unverified.json")
    for i in ("ww-55473766", "ww-59951280", "ww-65420022", "ww-55475350", "ww-57953021", "ww-62890200", "ww-63353220", "ww-64432641", "ww-55473488"):
        assert u[i]["call_check"] is True and u[i]["flag"] and u[i]["sign_url"]
    assert "07816" not in json.dumps(u["ww-55473488"])  # churchwarden's personal mobile never added

# Bot 4 browser batch 3 (28 Oct 2026)
def test_bot4_browser_batch3():
    fx = {f["id"]: f for f in J("overrides/warmspaces_fixes.json")}
    assert "Hope Street East" in fx["ww-68506647"]["address"] and fx["ww-64432678"]["address"].startswith("Hollybrook")
    u = J("overrides/warmspaces_unverified.json")
    assert u["ww-57951889"]["phone"] == "07876 372274" and u["ww-64432678"]["flag"]
    for i in ("ww-57951802", "ww-57952849", "ww-69175071", "ww-69068910", "ww-65437525", "ww-57951784", "ww-65441920"):
        assert u[i]["call_check"] is True and u[i]["flag"] and u[i]["sign_url"]
