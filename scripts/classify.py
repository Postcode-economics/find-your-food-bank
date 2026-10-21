"""Classify every food bank entry as client-facing, warehouse/office (donations only), donation drop-off only, or unclear.
Runs inside scripts/build.py on every nightly refresh, so new data is classified too. Only HIGH-confidence non-client
entries are relabelled on the map; unclear ones keep their normal pin and are only flagged in the audit CSV.
Manual entries in overrides/foodbank_manual.json always win (NEVER remove them)."""
import json, os, re, csv, collections
STRONG = re.compile(r"\b(warehouse|depot|industrial (estate|park|units?)|business (park|centre|center)|trading estate|enterprise (park|centre)|po box|head office)\b", re.I)
WEAK = re.compile(r"\b(office|admin(istration)?|unit \d+[a-z]?)\b", re.I)
VENUE = re.compile(r"\b(church|chapel|c/o|community|ministr\w*|liberty|hope|freedom|light|life|eternity|vineyard|centre for)\b", re.I)
LOCKW = re.compile(r"\b(warehouse|depot|head office|admin|donations? only|drop[- ]off|not a distribution)\b", re.I)
EN = "Donations drop-off – warehouse/office. Not a food bank: clients cannot visit."
CY = "Man gollwng rhoddion – warws/swyddfa. Nid banc bwyd: ni all cleientiaid ymweld."
DROP_EN = "Donation drop-off only. Not a food bank: clients cannot get food here."
DROP_CY = "Man gollwng rhoddion yn unig. Nid banc bwyd: ni all cleientiaid gael bwyd yma."
def classify(items, root):
    man = {k: v for k, v in json.load(open(os.path.join(root, "overrides", "foodbank_manual.json"))).items() if not k.startswith("_")} \
        if os.path.exists(os.path.join(root, "overrides", "foodbank_manual.json")) else {}
    locs = collections.defaultdict(list)
    for i in items:
        if i["type"] == "location": locs[i["id"].split("/")[0]].append(i)
    rows = []
    for i in items:
        txt = f"{i['name']} {i['address']}"; ot = i.get("opening_times") or {}
        times = "has opening times" if ot.get("status") == "TIMES_FOUND" else "no opening times listed"
        ev, kind, conf = [], "client", "medium"
        if i["type"] == "foodbank":
            n = len(locs[i["id"]]); s = STRONG.search(txt); w = WEAK.search(txt)
            if n: ev.append(f"Give Food lists {n} separate distribution location(s) for this food bank")
            if s: ev.append(f"address/name contains '{s.group(0)}'")
            elif w: ev.append(f"address/name contains '{w.group(0)}'")
            ev.append(times)
            v = VENUE.search(txt)
            if n and s and v: kind, conf = "unclear", "medium"; ev.append(f"but also names a venue ('{v.group(0)}'), which may serve clients")
            elif n == 1 and s: kind, conf = "unclear", "medium"; ev.append("only 1 separate location, so this site may also serve clients")
            elif n and s: kind, conf = "warehouse", "high"
            elif n and w: kind, conf = "unclear", "medium"   # likely office, not applied
            elif n: kind, conf = "unclear", "low"
            elif s: kind, conf = "unclear", "low"; ev.append("no separate locations, so this may be the only site")
            else: kind, conf = "client", "medium"; ev.append("only address listed for this food bank")
        else:
            ev.append("listed by Give Food as a distribution location of " + i["foodbank"]); kind, conf = "client", "high"
            m = LOCKW.search(txt)
            if m: kind, conf = "unclear", "low"; ev.append(f"name/address contains '{m.group(0)}'")
        if i["id"] in man:
            o = man[i["id"]]; kind, conf = o["kind"], "confirmed"; ev = [o["evidence"]]
        apply = conf in ("high", "confirmed") and kind in ("warehouse", "dropoff")
        en = cy = ""
        if kind in ("warehouse", "dropoff"):
            en, cy = (EN, CY) if kind == "warehouse" else (DROP_EN, DROP_CY)
            if i["id"] in man: en, cy = man[i["id"]]["label_en"], man[i["id"]]["label_cy"]
        for k in ("kind", "label_en", "label_cy", "centres", "locked"): i.pop(k, None)
        if apply:
            i["kind"] = kind; i["label_en"] = en; i["label_cy"] = cy
            i["centres"] = [{"id": l["id"], "name": l["name"], "address": l["address"], "lat": l["lat"], "lng": l["lng"]} for l in locs[i["id"].split("/")[0]] if l["id"] != i["id"]]
            if i["id"] in man:
                i["locked"] = True
                if man[i["id"]].get("drop_opening_times"): i["opening_times"] = None
        rows.append({"id": i["id"], "type": i["type"], "network": i.get("network") or "Independent", "name": i["name"], "address": i["address"],
            "current_label": "Food bank pin" if i["type"] == "foodbank" else "Food bank location pin",
            "class": {"client": "client-facing", "warehouse": "warehouse/office (donations only)", "dropoff": "donation drop-off only", "unclear": "unclear"}[kind],
            "proposed_label_en": en, "proposed_label_cy": cy, "applied": "yes" if apply else "no", "evidence": "; ".join(ev), "confidence": conf})
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
