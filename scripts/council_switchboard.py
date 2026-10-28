"""Dean's rule (27-28 Oct 2026): never use a council's general switchboard / contact-centre
number as a venue's direct line or out-of-hours line (shelters and warm spaces).

Known general numbers live in overrides/council_switchboards.json. Approved locked
out-of-hours lines (locked_ooh there, e.g. Ceredigion 0300 456 3554) are never blocked."""
import json, os, re
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PATH = os.path.join("overrides", "council_switchboards.json")
COUNCIL_FIELDS = ("council", "council_phone", "council_ooh", "council_url", "council_label", "council_label_cy")
_cache = {}

def digits(n):
    d = re.sub(r"\D", "", str(n or ""))
    return "0" + d[2:] if d.startswith("44") else d

def load(root=None):
    p = os.path.join(root or ROOT, PATH)
    if p not in _cache:
        d = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
        _cache[p] = ({digits(k) for k in d.get("switchboards", {})}, {digits(k) for k in d.get("locked_ooh", {})})
    return _cache[p]

def is_locked(number, root=None):
    return bool(digits(number)) and digits(number) in load(root)[1]

def is_general(number, root=None):
    """True when number is a known council switchboard and not an approved locked line."""
    d = digits(number)
    if not d: return False
    sw, locked = load(root)
    return d in sw and d not in locked

def strip(item, root=None):
    """Remove a council line that is a general number. Returns the blocked number or ''."""
    bad = next((item.get(k) for k in ("council_phone", "council_ooh") if is_general(item.get(k), root)), "")
    if bad:
        for k in COUNCIL_FIELDS: item.pop(k, None)
    return bad or ""
