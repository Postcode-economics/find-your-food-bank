"""Warm-space website field: keep only values that look like a web address (fault scan 28 Oct 2026).
The card turns the field into a link, so free text such as 'We do not have a website' or 'undefined' became https://We do not have a website."""
import re
URL = re.compile(r"^(https?://)?[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+(:\d+)?([/?#]\S*)?$")
def is_url(v):
    v = (v or "").strip()
    return bool(v) and v.lower() not in ("undefined", "null", "none") and bool(URL.match(v))
def clean(items):
    """Blank every website value that is not a URL. Returns [(id, old value)]."""
    out = []
    for x in items:
        v = x.get("website")
        if v and not is_url(v):
            out.append((x.get("id"), v)); x["website"] = ""
    return out
