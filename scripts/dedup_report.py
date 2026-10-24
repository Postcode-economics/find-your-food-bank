"""Point 6 (24 Oct 2026): duplicates already on the map. Groups entries by postcode and proposes merges for Dean in
reports/duplicates.md (+ logs/duplicates.json). Nothing is merged or removed automatically.
  'likely duplicate': same postcode and the names share a main word (or pins within 30 m)
  'same postcode, different service': everything else in a shared postcode (listed for information)."""
import json, math, os, re, collections
ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data.full.js"); MD = os.path.join(ROOT, "reports", "duplicates.md"); JS = os.path.join(ROOT, "logs", "duplicates.json")
STOP = {"foodbank", "food", "bank", "the", "of", "and", "centre", "center", "church", "community", "hub", "distribution", "salvation", "army", "trust", "st", "ni", "city", "-", "&"}
def words(n): return {w for w in re.findall(r"[a-z0-9']+", (n or "").lower()) if w not in STOP and len(w) > 2}
def dist(a, b):
    try: return 6371000 * math.hypot(math.radians(b["lat"] - a["lat"]), math.radians(b["lng"] - a["lng"]) * math.cos(math.radians(a["lat"])))
    except Exception: return None
def find(items):
    g = collections.defaultdict(list)
    for i in items:
        pc = re.sub(r"\s", "", (i.get("postcode") or "")).upper()
        if pc: g[pc].append(i)
    out = []
    for pc, v in sorted(g.items()):
        if len(v) < 2: continue
        for a_i in range(len(v)):
            for b_i in range(a_i + 1, len(v)):
                a, b = v[a_i], v[b_i]; d = dist(a, b)
                likely = bool(words(a.get("name")) & words(b.get("name"))) or (d is not None and d <= 30)
                out.append(dict(postcode=pc, a=a["id"], a_name=a.get("name"), b=b["id"], b_name=b.get("name"), metres=None if d is None else round(d), kind="likely duplicate" if likely else "same postcode, different service"))
    return out
def main():
    s = open(DATA, encoding="utf-8").read(); items = json.loads(s[s.index("{"): s.rindex("}") + 1])["items"]
    pairs = find(items); json.dump(pairs, open(JS, "w"), indent=1)
    L = ["# Possible duplicates on the map", "", "Proposed merges for Dean. Nothing is merged automatically.", ""]
    for k in ("likely duplicate", "same postcode, different service"):
        ps = [p for p in pairs if p["kind"] == k]; L += ["## %s (%d)" % (k, len(ps)), ""]
        L += ["- %s: %s (`%s`) / %s (`%s`), %s m apart" % (p["postcode"], p["a_name"], p["a"], p["b_name"], p["b"], p["metres"]) for p in ps] + [""]
    open(MD, "w", encoding="utf-8").write("\n".join(L)); return pairs
if __name__ == "__main__":
    p = main(); print("duplicates: %d likely, %d other" % (sum(x["kind"] == "likely duplicate" for x in p), sum(x["kind"] != "likely duplicate" for x in p)))
