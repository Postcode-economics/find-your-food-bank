"""Explicit who / referral / wheelchair fields from overrides and manual files.

A wheelchair value is copied only when a record states yes, partial or no.
Nothing is inferred from other facilities. 'Accessible Toilets' is a toilet
facility, not wheelchair access, and is left on the place's facility list.
"""
WHEEL = ("yes", "partial", "no")


def copy_wheelchair(dest, src):
    """Copy wheelchair, wheelchair_quote and wheelchair_source when src states them. Returns True if copied."""
    if not isinstance(dest, dict) or not isinstance(src, dict):
        return False
    w = src.get("wheelchair")
    if w not in WHEEL:
        return False
    dest["wheelchair"] = w
    for k in ("wheelchair_quote", "wheelchair_source"):
        v = src.get(k)
        if isinstance(v, str) and v.strip():
            dest[k] = v.strip()
        elif k in dest and k not in src:
            pass
    return True


def _copy_list_or_text(dest, src, key):
    """Copy a stated facilities/provided value. A list is copied as a list. A string is stored as a one-item list so facHtml does not split it into characters. Never wipes a value already on the item."""
    if dest.get(key):
        return
    raw = src.get(key)
    if isinstance(raw, list):
        stated = [item for item in raw if str(item or "").strip()]
        if stated:
            dest[key] = stated
    elif isinstance(raw, str) and raw.strip():
        dest[key] = [raw.strip()]


def stamp(items, overlays, fill_missing=False):
    """Copy an explicit wheelchair (and, if fill_missing, groups, referral, facilities and provided) from id-keyed overrides.

    Never invents a value. An overlay without wheelchair leaves the item unchanged.
    fill_missing only fills groups, referral, facilities or provided when the item does not already have them
    and the override states them.
    """
    if not isinstance(overlays, dict):
        return 0
    n = 0
    for x in items or []:
        src = overlays.get(x.get("id"))
        if not isinstance(src, dict) or src is x:
            continue
        if copy_wheelchair(x, src):
            n += 1
        if not fill_missing:
            continue
        if src.get("groups") and not x.get("groups"):
            x["groups"] = list(src["groups"])
            if src.get("groups_source"):
                x["groups_source"] = src["groups_source"]
        ref = src.get("referral")
        if isinstance(ref, str) and ref.strip() and not str(x.get("referral") or "").strip():
            x["referral"] = ref.strip()
        _copy_list_or_text(x, src, "facilities")
        _copy_list_or_text(x, src, "provided")
    return n
