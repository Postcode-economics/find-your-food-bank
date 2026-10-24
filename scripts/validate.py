"""Point 33 (24 Oct 2026): data validation before publishing - report-only core.
Checks every food bank, shelter and warm space for: (a) phone looks like a UK number, (b) opening times are valid
HH:MM ranges, (c) postcode matches the UK format, (d) name not empty. The single-word name rule is NOT applied
(1,000+ real places such as Trussell centres named after the town are one word).
Writes reports/validation.md + reports/validation.json. It never removes or blocks anything: new places are already
held by publish_gate.py; whether a failed check should block publishing is Dean's call. postcodes.io lookups stay in build_outcodes.py."""
import json, os, re, sys
ROOT = os.path.join(os.path.dirname(__file__), "..")
FILES = {"foodbanks": "data.full.js", "shelters": "shelters.js", "warmspaces": "warmspaces.js"}
PC = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
def phone_ok(p):
    parts = [x for x in re.split(r"\s+or\s+|/|,|;", p or "") if x.strip()]
    if len(parts) > 1: return all(phone_ok(x) for x in parts)
    d = re.sub(r"\D", "", p or "")
    if d.startswith("44"): d = "0" + d[2:]
    return bool(re.match(r"^0\d{9,10}$", d) or re.match(r"^(116\d{3}|999|111|101|105)$", d))
def times_ok(ot):
    st = (ot or {}).get("structured") if isinstance(ot, dict) else None
    if not st: return True
    for day, rngs in st.items():
        for r in rngs or []:
            if len(r) != 2 or not all(TIME.match(str(t)) for t in r) or r[0] >= r[1]: return False
    return True
def problems(i):
    out = []
    if (i.get("phone") or "").strip() and not phone_ok(i["phone"]): out.append("a phone")
    if not times_ok(i.get("opening_times") or i.get("hours")): out.append("b times")
    pc = (i.get("postcode") or "").strip().upper()
    if pc and not PC.match(pc): out.append("c postcode")
    if not (i.get("name") or "").strip(): out.append("d name")
    return out
def main():
    rep = {}
    for k, f in FILES.items():
        p = os.path.join(ROOT, f)
        if not os.path.exists(p): continue
        s = open(p, encoding="utf-8").read()
        for i in json.loads(s[s.index("{"): s.rindex("}") + 1]).get("items", []):
            pr = problems(i)
            if pr: rep.setdefault(k, []).append(dict(id=i.get("id"), name=i.get("name"), phone=i.get("phone"), postcode=i.get("postcode"), problems=pr))
    json.dump(rep, open(os.path.join(ROOT, "reports", "validation.json"), "w"), indent=1, ensure_ascii=False)
    L = ["# Validation report (point 33)", "", "Report only - nothing is blocked or removed.", ""]
    for k, v in rep.items(): L += ["## %s (%d)" % (k, len(v)), ""] + ["- %s (`%s`): %s - phone %s, postcode %s" % (x["name"], x["id"], ", ".join(x["problems"]), x["phone"], x["postcode"]) for x in v] + [""]
    open(os.path.join(ROOT, "reports", "validation.md"), "w", encoding="utf-8").write("\n".join(L)); return rep
if __name__ == "__main__": print("validation:", {k: len(v) for k, v in main().items()})
