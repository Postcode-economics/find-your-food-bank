"""Freeze listing phone numbers (Dean, 27 Oct 2026).

Every id in overrides/phone_baseline.json keeps the number recorded there.
Feed refresh, learning, auto-apply and phone fixes may not change it.
A different proposal is blocked, logged, and held for Dean. A blank never wipes a frozen number.
A brand-new id may publish its first number when it passes the UK check in hours_fix;
that number is then frozen too. Later changes wait for a reviewed edit of the baseline.

Council lines follow the same freeze, and a council with no verified out-of-hours
number has its council line hidden (never a daytime number).

Council-line fields (COUNCIL_FIELDS) are never added, changed, copied or removed by a job
(Dean, 29 Oct 2026). guard(published=...) keeps the last published bytes of each field.
A brand-new place has no council line until Dean OKs one. Anything else a refresh proposes
(the contacts overrides, settle_council, or a baseline that differs from the live file) is held
for Dean in reports/pending_dean.md. An OK'd change is a reviewed PR that edits the listing file
and overrides/phone_baseline.json together.
"""
import json, os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BASE_NAME = os.path.join("overrides", "phone_baseline.json")
FIELDS = ("phone", "tel", "council_phone", "council_ooh", "council_label", "council_label_cy")
COUNCIL_FIELDS = ("council_phone", "council_ooh", "council_label", "council_label_cy")
# A verified out-of-hours line says so. Daytime / switchboard wording is not enough.
OOH_MARKERS = ("out-of-hours", "out of hours", "emergency", "rough sleep", "sleeping rough", "nihe", "housing executive")
_cache = {}

def baseline_path(root=None):
    return os.path.join(root or ROOT, BASE_NAME)

def load(root=None):
    path = baseline_path(root)
    if not os.path.exists(path):
        return None
    m = os.path.getmtime(path)
    hit = _cache.get(path)
    if hit and hit[0] == m:
        return hit[1]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("listings", {})
    _cache[path] = (m, data)
    return data

def save(data, root=None):
    path = baseline_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    _cache[path] = (os.path.getmtime(path), data)

def is_listed(iid, root=None):
    data = load(root)
    return bool(data and iid in data["listings"])

def frozen(iid, root=None):
    data = load(root)
    if not data: return None
    return data["listings"].get(iid)

def _blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")

def uk_ok(number):
    """Same UK check the refresh uses before a number can be dialled (hours_fix.clean_phone)."""
    from hours_fix import clean_phone
    _disp, tel = clean_phone(number)
    return bool(tel)

def ooh_label(label):
    low = (label or "").lower()
    return any(m in low for m in OOH_MARKERS)

def snap(item, layer):
    rec = {"layer": layer}
    for f in FIELDS:
        v = item.get(f)
        if isinstance(v, str) and v.strip():
            rec[f] = v
    return rec

def settle_council(item):
    """Show a verified out-of-hours council line, byte for byte. Hide every other council line.
    Returns True when the item changed."""
    before = {k: item.get(k) for k in COUNCIL_FIELDS}
    ooh = (item.get("council_ooh") or "").strip()
    phone = (item.get("council_phone") or "").strip()
    label = item.get("council_label") or ""
    if ooh:
        if item.get("council_phone") != ooh:
            item["council_phone"] = ooh  # a different daytime council_phone is not shown
        if _blank(label):
            item["council_label"] = "Council out-of-hours emergency line"
    elif phone and ooh_label(label):
        item["council_ooh"] = phone
    else:
        for k in COUNCIL_FIELDS:
            item.pop(k, None)
    after = {k: item.get(k) for k in COUNCIL_FIELDS}
    return before != after

def _section(root, filename, tag, line):
    path = os.path.join(root or ROOT, "reports", filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    start, end = "<!-- %s -->" % tag, "<!-- /%s -->" % tag
    prev = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            prev = f.read()
    if start in prev and end in prev:
        pre, rest = prev.split(start, 1)
        mid, post = rest.split(end, 1)
        if line not in mid:
            mid = mid.rstrip() + "\n" + line + "\n"
        else:
            mid = mid if mid.endswith("\n") else mid + "\n"
        text = pre + start + "\n" + mid.lstrip("\n") + end + post
    else:
        text = prev.rstrip() + "\n\n" + start + "\n" + line + "\n" + end + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")

def hold(root, iid, field, stored, proposed, source, via, name=""):
    """Block one attempted change: pending_dean only (anomaly_brake.md is the stop report; a hold is not a stop). The stored bytes stay."""
    shown = proposed if not _blank(proposed) else "(blank)"
    kept = stored if not _blank(stored) else "(none)"
    line = "- blocked, held for Dean | %s | %s | via %s | source %s | stored %s | proposed %s | unchanged (byte-identical)" % (
        iid, field, via, source or "(none)", kept, shown)
    if name:
        line += " | " + name
    _section(root, "pending_dean.md", "phone lock", line)
    return False

def log_new(root, iid, number, source, via):
    line = "- new listing number | %s | %s | via %s | source %s" % (iid, number, via, source or "(none)")
    _section(root, "daily_review.md", "phone lock new", line)

def consider(item, field, proposed, root=None, via="auto-apply", source="", persist_new=False, layer=None):
    """Write `proposed` onto item[field] only when the rules allow it.
    Returns True when the proposed value was written."""
    root = root or ROOT
    iid = item.get("id")
    data = load(root)
    if data is None or not iid:
        return False
    if field in COUNCIL_FIELDS:
        cur = item.get(field)
        if proposed != cur:
            hold(root, iid, field, cur, proposed, source, via, item.get("name") or "")
        return False
    if iid in data["listings"]:
        cur = data["listings"][iid].get(field)
        if proposed == cur:
            return False
        if _blank(cur):
            item.pop(field, None)
        else:
            item[field] = cur  # exact baseline bytes, including spaces
        hold(root, iid, field, cur, proposed, source, via, item.get("name") or "")
        return False
    if field not in ("phone", "tel"):
        return False
    if _blank(proposed) or not uk_ok(proposed):
        return False
    item[field] = proposed
    if persist_new:
        data["listings"][iid] = snap(item, layer or item.get("layer") or "listings")
        save(data, root)
        log_new(root, iid, item.get("phone") or proposed, source, via)
    return True

def live_council(items):
    """Copy of each published item's council-line fields, taken before anything in the run can touch them."""
    return {i["id"]: {k: i[k] for k in COUNCIL_FIELDS if k in i} for i in items or [] if isinstance(i, dict) and i.get("id")}

def _by_id(published):
    if published is None:
        return None
    if isinstance(published, dict):
        return published
    return live_council(published)

def lock_council(item, pub, rec, root, via="refresh", source="feed refresh"):
    """Put back the council-line bytes that are live (pub), else the baseline (rec), else none.
    Every difference is held for Dean. Returns how many fields were held."""
    ref = pub if pub is not None else (rec or {})
    iid, name, n = item.get("id"), item.get("name") or "", 0
    for f in COUNCIL_FIELDS:
        prop = item.get(f)
        if f in ref:
            item[f] = ref[f]
        else:
            item.pop(f, None)
        if prop != ref.get(f) and not (_blank(prop) and _blank(ref.get(f))):
            hold(root, iid, f, ref.get(f), prop, source, via, name)
            n += 1
        if pub is not None and rec is not None and not (_blank(pub.get(f)) and _blank(rec.get(f))) and pub.get(f) != rec.get(f):
            hold(root, iid, f, pub.get(f), rec.get(f), BASE_NAME, via, name)
            n += 1
    return n

def guard(items, root=None, via="refresh", source="feed refresh", layer="", persist_new=False, published=None):
    """Keep frozen numbers. `published` is the live list (or id map) the council lines are locked to.
    Returns how many items were held or newly frozen."""
    root = root or ROOT
    data = load(root)
    if data is None:
        return 0
    n = 0
    listings = data["listings"]
    live = _by_id(published)
    changed_file = False
    for item in items:
        iid = item.get("id")
        if not iid:
            continue
        n += lock_council(item, live.get(iid) if live is not None else None, listings.get(iid), root, via, source)
        if iid in listings:
            rec = listings[iid]
            for field in FIELDS:
                if field in COUNCIL_FIELDS:
                    continue
                cur = rec.get(field)
                prop = item.get(field)
                if _blank(cur) and _blank(prop):
                    continue
                if prop == cur:
                    continue
                if _blank(cur):
                    item.pop(field, None)
                else:
                    item[field] = cur
                hold(root, iid, field, cur, prop, source, via, item.get("name") or "")
                n += 1
            continue
        phone = item.get("phone") or ""
        if _blank(phone) and _blank(item.get("tel")):
            continue
        candidate = phone if uk_ok(phone) else (item.get("tel") if uk_ok(item.get("tel") or "") else "")
        if not candidate:
            if not _blank(phone):
                item["phone"] = ""
            if item.get("tel"):
                item["tel"] = ""
            continue
        if not uk_ok(phone) and uk_ok(item.get("tel") or ""):
            item["phone"] = item.get("tel")
        if persist_new:
            listings[iid] = snap(item, layer or "listings")
            log_new(root, iid, item.get("phone") or item.get("tel") or "", source, via)
            changed_file = True
            n += 1
    if changed_file:
        save(data, root)
    return n
