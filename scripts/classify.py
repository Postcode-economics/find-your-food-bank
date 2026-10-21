"""Classify every food bank entry as client-facing, warehouse/office (donations only), donation drop-off only, or unclear.
Runs inside scripts/build.py on every nightly refresh, so new data is classified too. Only HIGH-confidence non-client
entries are relabelled on the map; unclear ones keep their normal pin and are only flagged in the audit CSV.
Manual entries in overrides/foodbank_manual.json always win (NEVER remove them)."""
import json, os, re, csv, collections
STRONG = re.compile(r"\b(warehouse|depot|industrial (estate|park|units?)|business (park|centre|center)|trading estate|enterprise (park|centre)|po box|head office)\b", re.I)
WEAK = re.compile(r"\b(office|admin(istration)?|unit \d+[a-z]?)\b", re.I)
VENUE = re.compile(r"\b(church|chapel|c/o|community|ministr\w*|liberty|hope|freedom|light|life|eternity|vineyard|centre for)\b", re.I)
LOCKW = re.compile(r"\b(warehouse|depot|head office|admin|donations? only|drop[- ]off|not a distribution)\b", re.I)
EN = "Donations only"
CY = "Rhoddion yn unig"
DROP_EN = EN
DROP_CY = CY
def add_extra_locations(items, root):
    """Client locations Give Food does not list (overrides/foodbank_extra_locations.json), checked on the food bank's own site.
    Added (or refreshed) as normal 'location' pins of their parent food bank. Idempotent."""
    p = os.path.join(root, "overrides", "foodbank_extra_locations.json")
    if not os.path.exists(p): return 0
    ex = {k: v for k, v in json.load(open(p)).items() if not k.startswith("_")}
    par = {i["id"]: i for i in items if i["type"] == "foodbank"}
    items[:] = [i for i in items if i["id"] not in ex]
    n = 0
    for k, x in ex.items():
        pa = par.get(x["parent"])
        if not pa: print("warning: extra location parent missing:", k); continue
        items.append({"id": k, "type": "location", "name": x["name"], "foodbank": pa["name"], "network": pa.get("network"), "address": x["address"],
            "postcode": x["postcode"], "lat": x["lat"], "lng": x["lng"], "phone": x.get("phone") or pa.get("phone") or "", "website": x.get("evidence_url") or pa.get("website") or "",
            "givefood": pa.get("givefood") or "", "opening_times": x.get("opening_times"), "pc_checked": True, "phone_checked": True, "manual": True, "evidence_url": x.get("evidence_url")})
        n += 1
    return n
def apply_address_fixes(items, root):
    """overrides/foodbank_address_fixes.json: correct a food bank's own pin to where food is given out; drop stale pins. Idempotent."""
    p = os.path.join(root, "overrides", "foodbank_address_fixes.json")
    if not os.path.exists(p): return
    fx = json.load(open(p)); rm = set(fx.get("_remove_ids", []))
    items[:] = [i for i in items if i["id"] not in rm]
    for i in items:
        f = fx.get(i["id"])
        if f and not i["id"].startswith("_"):
            for k in ("address", "postcode", "lat", "lng"): i[k] = f[k]
def classify(items, root):
    add_extra_locations(items, root)
    apply_address_fixes(items, root)
    man = {k: v for k, v in json.load(open(os.path.join(root, "overrides", "foodbank_manual.json"))).items() if not k.startswith("_")} \
        if os.path.exists(os.path.join(root, "overrides", "foodbank_manual.json")) else {}
    locs = collections.defaultdict(list)
    for i in items:
        if i["type"] == "location": locs[i["id"].split("/")[0]].append(i)
    chk = {k: v for k, v in json.load(open(os.path.join(root, "overrides", "foodbank_checks.json"))).items() if not k.startswith("_")} \
        if os.path.exists(os.path.join(root, "overrides", "foodbank_checks.json")) else {}
    pcn = lambda x: (x or "").replace(" ", "").upper()
    addn = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())[:15]
    # A parent whose address/postcode is one of its own distribution locations is the same place: keep one client pin (the location).
    drop = set()
    for i in items:
        if i["type"] == "foodbank" and locs[i["id"]] and i["id"] not in man:
            if any((pcn(l["postcode"]) and pcn(l["postcode"]) == pcn(i["postcode"])) or addn(l["address"]) == addn(i["address"]) for l in locs[i["id"]]):
                drop.add(i["id"])
    nonclient_ids = {k for k, v in chk.items() if v['result'] == 'office'}
    rows = []
    for i in items:
        txt = f"{i['name']} {i['address']}"; ot = i.get("opening_times") or {}
        times = "has opening times" if ot.get("status") == "TIMES_FOUND" else "no opening times listed"
        ev, kind, conf = [], "client", "medium"
        if i["id"] in drop:
            m = [l for l in locs[i["id"]] if (pcn(l["postcode"]) and pcn(l["postcode"]) == pcn(i["postcode"])) or addn(l["address"]) == addn(i["address"])][0]
            rows.append({"id": i["id"], "type": i["type"], "network": i.get("network") or "Independent", "name": i["name"], "address": i["address"],
                "current_label": "Food bank pin", "class": "client-facing (merged)", "proposed_label_en": "", "proposed_label_cy": "", "applied": "yes: duplicate pin removed",
                "evidence": f"same address/postcode as its own distribution location '{m['name']}' ({m['id']}), which keeps the client pin", "confidence": "high"})
            continue
        if i["type"] == "foodbank":
            n = len(locs[i["id"]]); s = STRONG.search(txt); w = WEAK.search(txt)
            if n: ev.append(f"Give Food lists {n} separate distribution location(s) and this address is not one of them")
            if s: ev.append(f"address/name contains '{s.group(0)}'")
            elif w: ev.append(f"address/name contains '{w.group(0)}'")
            ev.append(times)
            if n: kind, conf = "warehouse", "high"   # rule (Dean, 21 Oct 2026): parent pin with separate client locations = office/warehouse
            elif s or re.search(r"\boffice\b", txt, re.I): kind, conf = "unclear", "low"; ev.append("single address with office/industrial wording: not yet confirmed by the food bank's own site")
            else: kind, conf = "client", "medium"; ev.append("only address listed for this food bank")
        else:
            ev.append("listed by Give Food as a distribution location of " + i["foodbank"]); kind, conf = "client", "high"
            m = LOCKW.search(txt) or (re.search(r"\b(office|admin\w*|warehouse)\b", txt, re.I) if ot.get("status") != "TIMES_FOUND" else None)
            if m: kind, conf = "unclear", "low"; ev.append(f"name/address contains '{m.group(0)}'" + ("" if ot.get("status") == "TIMES_FOUND" else ", no opening times"))
        if i["id"] in chk:
            c = chk[i["id"]]; ev.append(f"checked 21 Oct 2026: {c['evidence']} ({c['url']})")
            kind, conf = {"office": ("warehouse", "high"), "client": ("client", "high"), "unclear": ("unclear", "low")}[c["result"]]
        if i["id"] in man:
            o = man[i["id"]]; kind, conf = o["kind"], "confirmed"; ev = [o["evidence"]]
        apply = conf in ("high", "confirmed") and kind in ("warehouse", "dropoff")
        en = cy = ""
        if kind in ("warehouse", "dropoff"):
            en, cy = (EN, CY) if kind == "warehouse" else (DROP_EN, DROP_CY)
            if i["id"] in man and man[i["id"]].get("locked"): en, cy = man[i["id"]]["label_en"], man[i["id"]]["label_cy"]  # only the locked B30 wording is kept; all others use the single label (Dean, 21 Oct 2026)
        for k in ("kind", "label_en", "label_cy", "centres", "locked"): i.pop(k, None)
        if apply:
            i["kind"] = kind; i["label_en"] = en; i["label_cy"] = cy
            pick = (man.get(i["id"]) or {}).get("centres", (chk.get(i["id"]) or {}).get("centres"))  # explicit list from a manual check wins
            near = sorted((l for l in locs[i["id"].split("/")[0]] if l["id"] != i["id"] and l["id"] not in nonclient_ids and (pick is None or l["id"] in pick)),
                          key=lambda l: (l["lat"] - i["lat"]) ** 2 + ((l["lng"] - i["lng"]) * 0.6) ** 2)[:12]  # nearest 12 client locations
            i["centres"] = [{"id": l["id"], "name": l["name"], "address": l["address"], "lat": l["lat"], "lng": l["lng"]} for l in near]
            if i["id"] in man:
                if man[i["id"]].get("locked"): i["locked"] = True
                if man[i["id"]].get("phone"): i["phone"] = man[i["id"]]["phone"]
                if man[i["id"]].get("drop_opening_times"): i["opening_times"] = None
        rows.append({"id": i["id"], "type": i["type"], "network": i.get("network") or "Independent", "name": i["name"], "address": i["address"],
            "current_label": "Food bank pin" if i["type"] == "foodbank" else "Food bank location pin",
            "class": {"client": "client-facing", "warehouse": "warehouse/office (donations only)", "dropoff": "donation drop-off only", "unclear": "unclear"}[kind],
            "proposed_label_en": en, "proposed_label_cy": cy, "applied": "yes" if apply else "no", "evidence": "; ".join(ev), "confidence": conf})
    items[:] = [i for i in items if i['id'] not in drop]
    return rows
def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
if __name__ == "__main__":  # re-classify the current data.js in place (no refetch)
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); p = os.path.join(root, "data.js")
    t = open(p).read(); d = json.loads(t[t.index("=") + 1:].strip().rstrip(";"))
    rows = classify(d["items"], root)
    open(p, "w").write("window.FB_DATA=" + json.dumps(d) + ";")
    write_csv(rows, sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "logs", "foodbank_audit.csv"))
    print(collections.Counter((r["class"], r["confidence"]) for r in rows))
