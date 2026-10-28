"""Pins and addresses stay where they were published (Dean, re-enable check).

A refresh may not move a pin (lat/lng) or rewrite an address or postcode.
A value Dean set in an override file may. Every other difference is put back
and listed for him in reports/pending_dean.md. Nothing here is auto-applied.
"""
import json, os, re
FIELDS = ("address", "postcode", "lat", "lng")
# About 20 m. Feed rounding inside this is the same pin: keep the published bytes, do not flag.
COORD_EPS = 0.0002
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
TAG = "address review"

def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def norm_text(v):
    return re.sub(r"\s+", " ", str(v or "").strip()).lower()

def norm_pc(v):
    return re.sub(r"\s+", "", str(v or "").strip()).upper()

def same(field, old, new):
    if field in ("lat", "lng"):
        if old in (None, "") and new in (None, ""):
            return True
        if old in (None, "") or new in (None, ""):
            return False
        try:
            return abs(float(old) - float(new)) <= COORD_EPS
        except (TypeError, ValueError):
            return False
    if field == "postcode":
        return norm_pc(old) == norm_pc(new)
    return norm_text(old) == norm_text(new)

def _blank(v):
    return v is None or (isinstance(v, str) and not v.strip())

def _section(root, lines, tag):
    """Replace one address-review section. An empty list removes it. Other sections stay.
    Leaves the file untouched when the text would not change."""
    path = os.path.join(root or ROOT, "reports", "pending_dean.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    original = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    prev = re.sub(r"(?s)\n*<!-- %s -->.*?<!-- /%s -->\n*" % (re.escape(tag), re.escape(tag)), "\n", original).rstrip("\n")
    if not lines:
        text = (prev + "\n") if prev.strip() else ""
    else:
        body = ["<!-- %s -->" % tag, "## Address and pin mismatches (not applied)", "",
                "The refresh saw a different address or pin. The published one was kept. Nothing below was written onto the map.", ""]
        body.extend(lines)
        body.append("<!-- /%s -->" % tag)
        base = prev if prev.strip() else "# Pending for Dean"
        text = base + "\n\n" + "\n".join(body) + "\n"
    if text == original:
        return
    if not text:
        if os.path.exists(path):
            os.remove(path)
        return
    open(path, "w", encoding="utf-8").write(text)

def flag_line(iid, field, stored, proposed, source, name=""):
    """One address/pin mismatch line. Does not change the listing or the report."""
    kept = stored if not _blank(stored) else "(none)"
    shown = proposed if not _blank(proposed) else "(none)"
    line = "- address mismatch, held for Dean | %s | %s | via %s | stored %s | proposed %s | unchanged" % (
        iid, field, source or "(none)", kept, shown)
    if name:
        return line + " | " + name
    return line

def write_flags(root, lines, tag=TAG):
    _section(root, lines, tag)

def _add_hand(out, iid, rec):
    if not iid or str(iid).startswith("_") or not isinstance(rec, dict):
        return
    slot = out.setdefault(iid, {})
    for f in FIELDS + ("hours", "opening_times"):
        if f in rec and not _blank(rec[f]):
            slot[f] = rec[f]

def hands(root, layer):
    """id -> {field: value} Dean set by hand. Generated snapshots are not in here."""
    root = root or ROOT
    out = {}
    base = os.path.join(root, "overrides")
    if layer == "foodbanks":
        for fn in ("foodbank_address_fixes.json", "foodbank_extra_locations.json",
                   "foodbank_added.json", "foodbank_approved_new.json"):
            data = _load(os.path.join(base, fn), {})
            if isinstance(data, dict):
                for k, v in data.items():
                    _add_hand(out, k, v)
    elif layer in ("shelters", "warmspaces"):
        man = _load(os.path.join(base, layer + "_manual.json"), [])
        if isinstance(man, list):
            for rec in man:
                if isinstance(rec, dict):
                    _add_hand(out, rec.get("id"), rec)
        elif isinstance(man, dict):
            for k, v in man.items():
                _add_hand(out, k, v if isinstance(v, dict) else {})
        ver = _load(os.path.join(base, layer + "_verified.json"), {})
        if isinstance(ver, dict):
            for k, v in ver.items():
                _add_hand(out, k, v)
        if layer == "warmspaces":
            fx = _load(os.path.join(base, "warmspaces_fixes.json"), [])
            if isinstance(fx, list):
                for rec in fx:
                    if isinstance(rec, dict):
                        _add_hand(out, rec.get("id"), rec)
            elif isinstance(fx, dict):
                for k, v in fx.items():
                    _add_hand(out, k, v)
    return out

def _restore(item, field, was):
    if _blank(was):
        item.pop(field, None)
    else:
        item[field] = was

def protect(items, previous, hand, root=None, source="refresh", keep_times=()):
    """Put published address/postcode/lat/lng back unless this value is Dean's hand-set one.
    For shelters and warm spaces, also put published hours back unless the times gate applied
    them this run (keep_times) or a hand-set override has this timetable.
    Returns how many fields were restored. Writes the review section (replacing last run's)."""
    root = root or ROOT
    prev = {}
    for old in previous or []:
        if isinstance(old, dict) and old.get("id"):
            prev[old["id"]] = old
    hand = hand or {}
    keep_times = set(keep_times or ())
    # Food-bank times live in overrides/opening_times.json and the strict gate. Shelter and warm-space
    # hours are rebuilt from a directory feed, so a feed timetable must not replace the published one.
    time_fields = () if source == "foodbanks" else ("hours",)
    lines = []
    n = 0
    for item in items or []:
        iid = item.get("id")
        old = prev.get(iid)
        if not old:
            continue
        allowed = hand.get(iid) or {}
        for field in FIELDS:
            new, was = item.get(field), old.get(field)
            if same(field, was, new):
                if field in ("lat", "lng") and was not in (None, "") and new != was:
                    _restore(item, field, was)  # keep the published bytes; not a move
                elif field in ("address", "postcode") and not _blank(was) and new != was and same(field, was, new):
                    _restore(item, field, was)
                continue
            if field in allowed and same(field, allowed[field], new):
                continue
            _restore(item, field, was)
            kept = was if not _blank(was) else "(none)"
            shown = new if not _blank(new) else "(none)"
            line = "- address mismatch, held for Dean | %s | %s | via %s | stored %s | proposed %s | unchanged" % (
                iid, field, source, kept, shown)
            if item.get("name"):
                line += " | " + item["name"]
            if line not in lines:
                lines.append(line)
            n += 1
        if iid in keep_times:
            continue
        allowed = hand.get(iid) or {}
        for field in time_fields:
            new, was = item.get(field), old.get(field)
            if _without_check_date(new) == _without_check_date(was):
                continue
            if field in allowed and _without_check_date(allowed[field]) == _without_check_date(new):
                continue
            _restore(item, field, was)
            line = "- times kept, not auto-applied | %s | %s | via %s | unchanged" % (iid, field, source)
            if item.get("name"):
                line += " | " + item["name"]
            if line not in lines:
                lines.append(line)
            n += 1
    write_flags(root, lines, "address review " + (source or "refresh"))
    return n

def _without_check_date(v):
    if not isinstance(v, dict):
        return v
    return {k: val for k, val in v.items() if k != "checked_date"}

def changes(old_items, new_items):
    """Counts of what a refresh would publish. Place fields are compared exactly after protect().
    opening_times / hours ignore a checked_date bump; that bump is counted on its own."""
    old = {i["id"]: i for i in old_items or [] if isinstance(i, dict) and i.get("id")}
    new = {i["id"]: i for i in new_items or [] if isinstance(i, dict) and i.get("id")}
    watched = FIELDS + ("name", "phone", "tel", "opening_times", "hours")
    out = {"added": len(set(new) - set(old)), "removed": len(set(old) - set(new)), "checked_date_only": 0}
    for field in watched:
        out[field] = 0
    for iid, item in new.items():
        was = old.get(iid)
        if not was:
            continue
        for field in watched:
            a, b = item.get(field), was.get(field)
            if field in ("opening_times", "hours"):
                if _without_check_date(a) != _without_check_date(b):
                    out[field] += 1
                elif a != b:
                    out["checked_date_only"] += 1
            elif a != b:
                out[field] += 1
    return out
