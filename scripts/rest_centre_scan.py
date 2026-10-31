"""Detect council incident rest-centre switch-on/off from visible page text (SWEP handled elsewhere)."""
import datetime, re

SWEP = re.compile(r"\bSWEP\b|severe weather emergency protocol|rough sleeper shelter", re.I)
PLAN = re.compile(r"\b(plan|guidance|what to do)\b", re.I)
PDF = re.compile(r"\.pdf\b", re.I)
DATE_NEAR = re.compile(
    r"\b(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4}|"
    r"(mon|tues|wednes|thurs|fri|satur|sun)day\s+\d{1,2}|updated?\s+(on\s+)?\d|:\s*\d{1,2}:\d{2})\b",
    re.I,
)

CENTRE = r"(?:rest centre|reception centre|emergency assistance centre|survivor reception centre|evacuation centre|emergency shelter)"
OFF = re.compile(
    rf"\b{CENTRE}\b[^.\n]{{0,140}}\b(has closed|is now closed|is closed|stood down)\b|"
    r"\b(residents can return to their homes)\b|"
    r"\b(?:[\w']+\s+){0,4}warning no longer in force\b|"
    r"\bno longer in force\b|"
    rf"\b{CENTRE}\b[^.\n]{{0,80}}\bstood down\b",
    re.I,
)
ON = re.compile(
    rf"\b(?:opened|has opened|have opened|opens)\s+(?:a|the|an)\s+(?:{CENTRE})\b|"
    rf"\b(?:{CENTRE})\b[^.\n]{{0,160}}\b("
    r"has been opened|has been set up|has been made available|is open|remains open|remains available|"
    r"is now available|has opened|opened|opens|is now open|made available"
    r")\b|"
    rf"\b(?:survivor reception centre)\b[^.\n]{{0,120}}\bopened\b|"
    rf"\b(?:emergency assistance centre)\b[^.\n]{{0,120}}\bopened\b",
    re.I,
)
HUMANITARIAN = re.compile(r"\bhumanitarian assistance centre\b", re.I)
MAJOR_ONLY = re.compile(r"\bmajor incident declared\b", re.I)
EVAC_ONLY = re.compile(r"\bevacuat\w*\b", re.I)
POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[\dA-Z]?\s*\d[A-Z]{2})\b")


def _norm(t):
    return re.sub(r"\s+", " ", t or "").strip()


def is_planning_page(text, url=None):
    t = _norm(text)
    u = (url or "").lower()
    if PDF.search(u):
        return True
    if PLAN.search(t) and not DATE_NEAR.search(t[:1200]):
        return True
    if PLAN.search(t) and not ON.search(t):
        return True
    return False


def rest_centre_off(text):
    t = _norm(text)
    if SWEP.search(t) and not re.search(CENTRE, t, re.I):
        return False
    return bool(OFF.search(t))


def _on_windows(text):
    t = text or ""
    return [t[max(0, m.start() - 240): m.end() + 100] for m in ON.finditer(t)]


def _stale_on(text, today=None):
    """An ON phrase that only sits next to an old date is a past notice, not a rest centre that is open now."""
    windows = _on_windows(text)
    if not windows:
        return False
    today = today or datetime.date.today()
    import seasonal
    saw_date = False
    for window in windows:
        ds = seasonal._all(window)
        if not ds:
            return False
        saw_date = True
        if (today - max(ds)).days <= 10:
            return False
    return saw_date


def rest_centre_on(text, today=None):
    """True only when council wording opens a rest/reception centre (not SWEP, not planning-only, not evac alone)."""
    t = _norm(text)
    if not t or SWEP.search(t) and not re.search(CENTRE, t, re.I):
        return False
    if HUMANITARIAN.search(t) and not re.search(rf"\b(?:{CENTRE})\b", t, re.I):
        return False
    if is_planning_page(t):
        return False
    if rest_centre_off(t):
        return False
    if not ON.search(t):
        if MAJOR_ONLY.search(t) or EVAC_ONLY.search(t):
            return False
        return False
    if MAJOR_ONLY.search(t) and not ON.search(t):
        return False
    if _stale_on(t, today):
        return False
    return True


def extract_postcode(text):
    m = POSTCODE.search(text or "")
    return m.group(1).upper() if m else ""
