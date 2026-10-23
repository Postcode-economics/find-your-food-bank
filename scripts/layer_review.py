"""Daily review list for shelters + warm spaces (Dean's rules: only uncertain or changed items go to Dean).
Compares the published layer files with the previous commit (or given files) and the recheck/SWEP logs.
Writes reports/layers_review.md and reports/layers_review.json. Never changes data.
Usage: python scripts/layer_review.py [--old-dir DIR]   (DIR holds the previous shelters.js / warmspaces.js)"""
import json, os, sys, subprocess
VARS = {"shelters.js": "SHELTERS", "warmspaces.js": "WARMSPACES"}
FIELDS = ("name", "address", "postcode", "lat", "lng", "phone", "hours", "tier", "access_type", "referral", "scheme_dates", "season", "ended", "upcoming")
def parse(s): return json.loads(s[s.index("{"): s.rindex("}") + 1]) if s and "{" in s else {"items": [], "recently_closed": []}
def load_old(f, old_dir):
    if old_dir: return parse(open(os.path.join(old_dir, f)).read())
    try: return parse(subprocess.run(["git", "show", "HEAD:" + f], capture_output=True, text=True).stdout)
    except Exception: return {"items": []}
def diff(old, new):
    o = {x["id"]: x for x in old.get("items", [])}; n = {x["id"]: x for x in new.get("items", [])}
    ch = []
    for k in set(o) & set(n):
        f = [x for x in FIELDS if o[k].get(x) != n[k].get(x)]
        if f: ch.append({"id": k, "name": n[k]["name"], "fields": f, "before": {x: o[k].get(x) for x in f}, "after": {x: n[k].get(x) for x in f}})
    return {"added": [{"id": k, "name": n[k]["name"], "tier": n[k].get("tier")} for k in sorted(set(n) - set(o))],
            "removed": [{"id": k, "name": o[k]["name"], "reason": next((c.get("closed_reason", "") for c in new.get("recently_closed", []) if c["id"] == k), "not confirmed this run")} for k in sorted(set(o) - set(n))],
            "changed": sorted(ch, key=lambda c: c["name"].lower()),
            "tier_flips": [c for c in ch if "tier" in c["fields"]],
            "upcoming": [x["name"] + " – " + x.get("scheme_dates", "") for x in n.values() if x.get("upcoming")],
            "ended": [x["name"] for x in n.values() if x.get("ended")]}
def main(old_dir=None):
    out = {}
    for f, v in VARS.items():
        new = parse(open(f).read()) if os.path.exists(f) else {"items": []}
        out[f] = diff(load_old(f, old_dir), new)
        rc = f"logs/{f.split('.')[0]}_recheck.json"
        if os.path.exists(rc):
            r = json.load(open(rc)); r.pop("_run", None)
            out[f]["recheck_failed"] = [{"id": k, "reason": e.get("reason")} for k, e in r.items() if isinstance(e, dict) and not e.get("ok")]
    sw = json.load(open("logs/swep_status.json")) if os.path.exists("logs/swep_status.json") else {}
    out["swep"] = {"active": sw.get("active", []), "changes": sw.get("changes", [])}
    os.makedirs("reports", exist_ok=True)
    json.dump(out, open("reports/layers_review.json", "w"), indent=1, ensure_ascii=False)
    L = ["# Shelters & warm spaces – review list", ""]
    for f in VARS:
        d = out[f]; L += [f"## {f}", f"added {len(d['added'])} · removed {len(d['removed'])} · changed {len(d['changed'])} · tier flips {len(d['tier_flips'])} · opens later {len(d['upcoming'])} · season ended {len(d['ended'])} · recheck failed {len(d.get('recheck_failed', []))}", ""]
        for x in d["removed"]: L.append(f"- REMOVED **{x['name']}** – {x['reason']}")
        for x in d["tier_flips"]: L.append(f"- TIER **{x['name']}**: {x['before'].get('tier')} → {x['after'].get('tier')}")
        for x in d["upcoming"]: L.append(f"- OPENS LATER {x}")
        L.append("")
    L += ["## SWEP", "Active: " + (", ".join(out["swep"]["active"]) or "none found")] + [f"- {c['council']}: {c['from']} → {c['to']} ({c['url']}) “{c['quote'][:160]}”" for c in out["swep"]["changes"]]
    open("reports/layers_review.md", "w").write("\n".join(L) + "\n")
    return out
if __name__ == "__main__":
    o = main(sys.argv[2] if sys.argv[1:2] == ["--old-dir"] else None)
    for f in VARS: print(f, {k: len(v) for k, v in o[f].items()})
