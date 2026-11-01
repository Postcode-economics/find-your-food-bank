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


def stamp(items, overlays, fill_missing=False):
    """Copy an explicit wheelchair (and, if fill_missing, groups and referral) from id-keyed overrides.

    Never invents a value. An overlay without wheelchair leaves the item unchanged.
    fill_missing only fills groups or referral when the item does not already have them
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
    return n
