"""Rule 21 (Dean, 26 Oct 2026, 08:29 GMT).

A verified number that the venue's own source page gives as its contact is shown,
including a named person's or personal number, with the label that page gives.
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

def own_page_source(rec):
    """True when the source record is the venue's own page, not a directory or register."""
    if not isinstance(rec, dict): return False
    if rec.get("own_page") is True: return True
    return bool(OWN_NOTE.search(rec.get("note") or ""))

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
