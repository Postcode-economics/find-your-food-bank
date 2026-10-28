"""Rule 21 (Dean, 26 Oct 2026, 08:29 GMT).

A verified number that the venue's own source page gives as its contact is shown,
including a named person's or personal number, with the label that page gives.
A host church's contact page counts as that venue's own page (Dean 26 Oct 2026, 08:37) ONLY when the
food bank has no own site (Dean 28 Oct 2026, PR #243). The food bank's own domain is read first; while
it still shows the stored number, a different number on the church page is held.
A number written next to a shop, office, helpline, school or similar (OTHER_LINE) is doubtful and held,
and so is a number on a page that never mentions a food bank or the listing's name.
An unverified or doubtful number is held, and the reason is recorded.
Dean's own details are never published.

named_person / personal are not reasons to hold a verified contact. Callers may
still pass those flags; decide() does not read them.
"""
import json, os, re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HOLDS = os.path.join(ROOT, "overrides", "phone_holds.json")
NEVER = os.path.join(ROOT, "overrides", "never_publish.json")
DEAN_REASON = "Dean's own details are never published"
PHONE_RE = re.compile(r"(?<!\d)(?:\+44\s?\(?0?\)?|0)(?:\d[\s-]?){9,10}(?!\d)")
OWN_NOTE = re.compile(
    r"confirmed live|own site|own website|own line|own landline|own contact|"
    r"contact page|site footer publishes",
    re.I)
PERSONAL_ONLY = re.compile(
    r"^(named[- _]?person|personal(?: number)?|private(?: number)?|named contact)$", re.I)
ROLES = ("Team Rector", "Team Vicar", "Priest-in-Charge", "Churchwarden",
         "Rector", "Vicar", "Pastor", "Minister", "Priest", "Imam", "Rabbi", "Chaplain")

def digits(s):
    d = re.sub(r"\D", "", s or "")
    if d.startswith("0044"): d = "0" + d[4:]
    elif d.startswith("44"): d = "0" + d[2:]
    return d

def _load(path):
    try: return json.load(open(path, encoding="utf-8"))
    except Exception: return {}

def load_block(path=None):
    raw = _load(path or NEVER)
    phones = {digits(x) for x in raw.get("phones") or [] if digits(x)}
    emails = set()
    for x in raw.get("emails") or []:
        e = str(x).strip().lower()
        if e and not e.startswith("_"): emails.add(e)
    return phones, emails

def is_dean(phone="", email="", text="", block=None):
    phones, emails = load_block() if block is None else block
    d = digits(phone)
    if d and d in phones: return True
    blob = digits(text)
    if blob and any(p and p in blob for p in phones): return True
    em = (email or "").strip().lower()
    if em and em in emails: return True
    low = (text or "").lower()
    return any(e and e in low for e in emails)

def personal_only(reason):
    return bool(PERSONAL_ONLY.match((reason or "").strip()))

def _host(u):
    return re.sub(r"^www\.", "", re.sub(r"^[a-z]+://", "", (u or "").strip().lower()).split("/")[0].split(":")[0])

def same_host(a, b):
    a, b = _host(a), _host(b)
    return bool(a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)))

HOST_CHURCH = re.compile(r"host church|church contact|church page|parish|church office", re.I)
def host_church_record(rec):
    return isinstance(rec, dict) and (rec.get("host_church") is True or bool(HOST_CHURCH.search(rec.get("note") or "")))

def host_church_counts(church_url, own_site=""):
    """A host church page is the food bank's own page only when the food bank has no own site (Dean 28 Oct 2026)."""
    return not own_site or same_host(church_url, own_site)

def own_page_source(rec, own_site=""):
    """True when the source record is the venue's own page, not a directory or register.
    A host church page does not count when the food bank has its own site on another host."""
    if not isinstance(rec, dict): return False
    if host_church_record(rec) and not host_church_counts(rec.get("source") or "", own_site or rec.get("own_site") or ""):
        return False
    if rec.get("own_page") is True: return True
    return bool(OWN_NOTE.search(rec.get("note") or ""))

def church_page_reasons(stored, church_url, church_phone, own_site="", own_site_phones=None):
    """Reasons a number read on a host church page must be held. The food bank's own domain is read first."""
    why = []
    if own_site and not same_host(church_url, own_site):
        why.append("the food bank has its own site (%s); a host church page is not its own page" % _host(own_site))
        if digits(stored) and digits(stored) in {digits(p) for p in own_site_phones or []}:
            why.append("the stored number is still shown on the food bank's own site")
    if digits(church_phone) and digits(stored) == digits(church_phone): why = []
    return why

OTHER_LINE = re.compile(
    r"charity shop|\bshops?\b|caf[eé]s?\b|head office|registered office|parish office|\boffices?\b|\badmin\w*|"
    r"help ?lines?\b|switchboard|dioces[ae]n?|\bdonations?\b|warehouse|furniture|nursery|\bschools?\b", re.I)
CONTEXT = 60
def other_line_reason(text, phone, width=CONTEXT):
    """'number sits next to <word>' when an occurrence of the number has a shop/office/helpline/... word within ~60 chars."""
    want = digits(phone)
    if not want: return ""
    for m in PHONE_RE.finditer(text or ""):
        if digits(m.group(0)) != want: continue
        near = (text[max(0, m.start() - width):m.start()] + " " + text[m.end():m.end() + width])
        w = OTHER_LINE.search(near)
        if w: return "number sits next to '%s' on the page (not the food bank's own line)" % w.group(0).strip().lower()
    return ""

FOODBANK_WORDS = re.compile(r"food[\s-]?banks?|food (?:parcels?|pantry|hub)", re.I)
def _flat(s): return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().replace("\u2019", "'").replace("'", "")).strip()
def mentions_food_bank(text, names=()):
    """The page says 'food bank' (or foodbank / food parcel / pantry), or gives the listing's full name."""
    if FOODBANK_WORDS.search(text or ""): return True
    flat = " " + _flat(text) + " "
    return any(len(_flat(n)) >= 6 and " " + _flat(n) + " " in flat for n in names or () if n)

def role_on(line):
    """The role written on this line, in the page's own wording. Empty when the line gives none."""
    hits = []
    for role in ROLES:
        m = re.search(r"\b" + re.escape(role) + r"\b", line or "", re.I)
        if m: hits.append(m.group(0))
    return max(hits, key=len) if hits else ""

def labels_in_text(text, norm=None):
    """Map an 11-digit UK number to the role on its own line. The first role wins."""
    norm = norm or (lambda p: digits(p) if len(digits(p)) == 11 and digits(p).startswith("0") else "")
    found = {}
    for line in (text or "").splitlines():
        for m in PHONE_RE.finditer(line):
            p = norm(m.group(0))
            if not p or p in found: continue
            lab = role_on(line)
            if lab: found[p] = lab
    return found

def decide(cand, block=None):
    """Return {action, phone, label, reason}. action is 'show' or 'hold'.

    A verified contact is shown, including when the page names a person. A hold
    needs a recorded reason that is not merely that the number is personal.
    """
    phone = (cand.get("phone") or "").strip()
    label = (cand.get("label") or "").strip()
    reason = (cand.get("reason") or "").strip()
    if personal_only(reason): reason = ""
    if is_dean(phone, cand.get("email") or "", cand.get("text") or "", block):
        return {"action": "hold", "phone": "", "label": "", "reason": DEAN_REASON}
    verified = bool(cand.get("verified"))
    doubtful = bool(cand.get("doubtful")) or bool(reason)
    if verified and not doubtful:
        return {"action": "show", "phone": phone, "label": label, "reason": ""}
    if not reason:
        reason = "unverified" if not verified else "doubtful"
    return {"action": "hold", "phone": "", "label": "", "reason": reason}

def phones_to_apply(phones, sources, holds, block=None):
    """Checked override numbers to copy onto places. A real hold reason keeps one off.
    A reason that only says the number is personal does not."""
    out = {}
    holds = holds or {}
    sources = sources or {}
    for i, num in (phones or {}).items():
        if str(i).startswith("_"): continue
        src = sources.get(i) if isinstance(sources.get(i), dict) else {}
        hold = holds.get(i) if isinstance(holds.get(i), dict) else {}
        reason = (hold.get("reason") or "").strip()
        doubtful = bool(reason) and not personal_only(reason)
        verified = hold.get("verified") is not False
        d = decide({"phone": num, "own_page": own_page_source(src), "verified": verified,
                    "doubtful": doubtful, "reason": reason if doubtful else "", "label": ""}, block)
        if d["action"] == "show": out[i] = num
    return out

def suppress(items, holds, block=None):
    """Clear a place's phone when it is Dean's, or the held doubtful number for that place."""
    n = 0
    holds = holds or {}
    for i in items:
        phone = i.get("phone") or ""
        h = holds.get(i.get("id")) if isinstance(holds.get(i.get("id")), dict) else None
        reason = ((h or {}).get("reason") or "").strip()
        clear = is_dean(phone, i.get("email") or "", block=block)
        if not clear and h and reason and not personal_only(reason) and digits(phone) and digits(phone) == digits(h.get("phone")):
            clear = True
        if clear:
            i["phone"] = ""; i["tel"] = ""; i.pop("phone_label", None); n += 1
    return n

def audit(cands):
    """Verified own-page numbers that were not shown and have no recorded reason.
    A personal-only note is not a recorded reason. Dean's details are a recorded reason
    when the hold text is the Dean reason."""
    bad = []
    for c in cands:
        if not (c.get("verified") and c.get("own_page")): continue
        if c.get("shown"): continue
        reason = (c.get("reason") or "").strip()
        if reason == DEAN_REASON: continue
        if is_dean(c.get("phone") or "", c.get("email") or "", c.get("text") or "") and reason == DEAN_REASON:
            continue
        if not reason or personal_only(reason): bad.append(c)
    return bad

def override_candidates(root=None):
    """Food-bank source rows whose note says the venue's own page confirmed the number."""
    root = root or ROOT
    ov = os.path.join(root, "overrides")
    phones, sources, holds = _load(os.path.join(ov, "phones.json")), _load(os.path.join(ov, "phone_sources.json")), _load(os.path.join(ov, "phone_holds.json"))
    out = []
    for i, src in sources.items():
        if str(i).startswith("_") or not isinstance(src, dict): continue
        if not own_page_source(src): continue
        if not str(src.get("source") or "").startswith("http"): continue
        hold = holds.get(i) if isinstance(holds.get(i), dict) else {}
        reason = (hold.get("reason") or "").strip()
        want = src.get("phone") or phones.get(i) or ""
        shown = i in phones and digits(phones.get(i)) == digits(want)
        if reason and not personal_only(reason) and digits(hold.get("phone")) == digits(want):
            shown = False
        out.append({"id": i, "phone": want, "own_page": True, "verified": hold.get("verified") is not False,
                     "shown": shown, "reason": reason})
    return out
