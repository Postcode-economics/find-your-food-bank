"""Flag shelter numbers that are a council's general line (Dean, 27 Oct 2026 23:49).
A shelter may only show its own direct line, or a genuine out-of-hours / emergency housing line quoted as such.
Never a switchboard, general enquiries or Housing Options main (daytime) line.
This check only REPORTS (reports/shelter_council_numbers.md + logs/shelter_council_numbers.json). It never removes a number.
Flags:
  1. shelter phone = a known council general number (overrides/council_general_numbers.json, each with its source quote)
  2. shelter phone = a council's daytime/main line held in overrides/shelters_contacts.json (council_phone)
  3. the published council line (council_ooh / council_phone) = a council daytime/main line (out-of-hours must be a quoted OOH number)"""
import json, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def digits(p): d = re.sub(r"\D", "", str(p or "")); return "0" + d[2:] if d.startswith("44") else d
def numbers(p): return [digits(x) for x in re.split(r"\s+or\s+|/|,|;", str(p or "")) if len(digits(x)) >= 10]
def known(root=ROOT):
    k = {}
    p = os.path.join(root, "overrides", "council_general_numbers.json")
    for n, v in (json.load(open(p)) if os.path.exists(p) else {}).items():
        if not n.startswith("_"): k[digits(n)] = dict(v, why="known council general number")
    c = os.path.join(root, "overrides", "shelters_contacts.json")
    C = json.load(open(c)) if os.path.exists(c) else {}
    # council_phone equal to council_ooh is that council's out-of-hours line stored in both fields, not a daytime line
    for area, v in (C.get("_councils") or {}).items():
        if v.get("council_phone"): k.setdefault(digits(v["council_phone"]), {"council": v.get("council"), "source": v.get("council_url"), "why": "council daytime/main line (" + area + ")",
                                                                              "ooh": digits(v["council_phone"]) == digits(v.get("council_ooh"))})
    for i, v in C.items():
        if not i.startswith("_") and isinstance(v, dict) and v.get("council_phone"):
            k.setdefault(digits(v["council_phone"]), {"council": v.get("council"), "source": v.get("council_url"), "why": "council daytime/main line",
                                                      "ooh": digits(v["council_phone"]) == digits(v.get("council_ooh"))})
    return k
def check(items, root=ROOT):
    K = known(root); out = []
    for x in items:
        for n in numbers(x.get("phone")):  # a shelter's own phone must not be any council line, out-of-hours included
            if n in K:
                f = {k: v for k, v in K[n].items() if k != "ooh"}
                if K[n].get("ooh"): f["why"] = "council out-of-hours line shown as the shelter's own phone"
                out.append({"id": x["id"], "name": x.get("name"), "field": "phone", "number": x.get("phone"), **f})
        for fld in ("council_ooh", "council_phone"):  # the published council line must be an out-of-hours one, never the daytime main line
            n = digits(x.get(fld))
            if x.get(fld) and n in K and not K[n].get("ooh"):
                out.append({"id": x["id"], "name": x.get("name"), "field": fld, "number": x[fld], **{k: v for k, v in K[n].items() if k != "ooh"},
                            "why": "shown as the out-of-hours line but is " + K[n]["why"]})
    seen, uniq = set(), []
    for f in out:
        k = (f["id"], digits(f["number"]))
        if k not in seen: seen.add(k); uniq.append(f)
    return uniq
def report(flags, root=ROOT, day=""):
    os.makedirs(os.path.join(root, "logs"), exist_ok=True); os.makedirs(os.path.join(root, "reports"), exist_ok=True)
    json.dump({"day": day, "count": len(flags), "flags": flags}, open(os.path.join(root, "logs", "shelter_council_numbers.json"), "w"), indent=1, ensure_ascii=False)
    md = ["# Shelter numbers that look like a council general line (%s)" % day, "",
          "Review only: nothing is removed automatically. A shelter may show only its own line or a quoted out-of-hours/emergency line.", ""]
    md += ["- **%s** (`%s`) %s %s: %s (%s; %s)" % (f["name"], f["id"], f["field"], f["number"], f["why"], f.get("council") or "", f.get("source") or "") for f in flags] or ["None."]
    open(os.path.join(root, "reports", "shelter_council_numbers.md"), "w").write("\n".join(md) + "\n")
if __name__ == "__main__":
    import datetime
    t = open(os.path.join(ROOT, "shelters.js")).read(); d = json.loads(t[t.index("{"):t.rindex("}") + 1])
    f = check(d["items"]); report(f, day=datetime.date.today().isoformat())
    for x in f: print(x["id"], x["field"], x["number"], "-", x["why"])
    print(len(f), "flagged")
