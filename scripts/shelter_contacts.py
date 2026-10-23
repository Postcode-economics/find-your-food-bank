"""Merge overrides/shelters_contacts.json into shelter items (run on every build so refreshes keep the numbers).
Fills phone/email only when the source has none; adds council referral line (council, council_phone, council_ooh, council_url)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from hours_fix import apply_phone
PATH = os.path.join(os.path.dirname(__file__), "..", "overrides", "shelters_contacts.json")

def load(path=PATH):
    return json.load(open(path)) if os.path.exists(path) else {}

def apply(items, data=None):
    data = load() if data is None else data
    councils = data.get("_councils", {})
    n = 0
    for x in items:
        o = data.get(x.get("id"))
        if not o: continue
        if o.get("phone_fix"):  # checked correction: always wins over the source number
            if x.get("phone") != o["phone_fix"]: x["phone_was"] = x.get("phone", "")
            x["phone"] = o["phone_fix"]; apply_phone(x); x["phone_source"] = o.get("phone_source", ""); n += 1
        elif o.get("drop_phone"):  # source number not on any official page: hide it, council/national fallback shows instead
            x["phone_was"] = x.get("phone", ""); x["phone"] = ""; x["tel"] = ""
        elif o.get("phone") and not x.get("tel"):
            x["phone"] = o["phone"]; apply_phone(x); x["phone_source"] = o.get("phone_source", ""); n += 1
        if o.get("hours") and not x.get("hours"):  # hand-checked hours / access line (Dean: no blank hours)
            x["hours"] = o["hours"]; x["hours_source"] = o.get("hours_source", ""); x["hours_checked"] = o.get("hours_checked", "")
        if o.get("email") and not x.get("email"): x["email"] = o["email"]
        if o.get("groups"): x["groups"] = o["groups"]; x["groups_source"] = o.get("groups_source", "")  # who it is for, hand-checked from own/operator page
        if o.get("referral_note"): x["referral"] = o["referral_note"]  # hand-checked: says whose phone line it is (no UI change)
        c = councils.get(o.get("area") or "") or {k: o[k] for k in ("council", "council_phone", "council_ooh", "council_url", "council_label", "council_label_cy") if o.get(k)}
        if c:
            for k, v in c.items(): x[k] = v
    return n

WS = os.path.join(os.path.dirname(__file__), "..", "overrides", "warmspaces_contacts.json")

def check(items):
    """Every entry must have a direct number or a labelled council fallback. Returns the ids that fail."""
    return [x["id"] for x in items if not x.get("tel") and not x.get("council_phone")]

if __name__ == "__main__" and sys.argv[1:2] == ["check"]:  # CI: fail if any entry has neither a number nor a labelled fallback
    bad = []
    for lay in ("shelters", "warmspaces"):
        t = open(os.path.join(os.path.dirname(__file__), "..", lay + ".js")).read(); d = json.loads(t[t.index("{"):t.rindex("}") + 1])
        bad += [lay + ":" + i for i in check(d["items"])]
    print("entries with no phone and no labelled fallback:", bad or "none"); sys.exit(1 if bad else 0)
elif __name__ == "__main__":  # apply to the published file in place: shelter_contacts.py [shelters|warmspaces]
    lay = sys.argv[1] if len(sys.argv) > 1 else "shelters"
    f = os.path.join(os.path.dirname(__file__), "..", lay + ".js"); s = open(f).read()
    pre, body = s[:s.index("{")], s[s.index("{"):s.rindex("}") + 1]; d = json.loads(body)
    print("filled", apply(d["items"], load(WS if lay == "warmspaces" else PATH)), "missing", check(d["items"]))
    open(f, "w").write(pre + json.dumps(d, ensure_ascii=False, separators=(",", ":")) + s[s.rindex("}") + 1:])
