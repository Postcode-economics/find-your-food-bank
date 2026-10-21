"""Fix 12-hour clock times that directories (notably the Warm Welcome feed) store as 24h without the pm shift,
e.g. '09:30 - 05:00' (meant 9.30am-5pm) or '01:30 - 07:00' (meant 1.30pm-7pm). Added 21 Oct 2026.
Rules, per span 'HH:MM - HH:MM' (a day may hold several spans joined by ' / '):
  * '00:00 - 00:00' is a blank placeholder: dropped.
  * open before 07:00 and close at/under 12:59 with close > open: both are pm (+12h), e.g. 04:30-06:00 -> 16:30-18:00.
  * close at or before open (close earlier on the 12h clock, or equal = ambiguous): close +12h when that makes
    it later than the open, e.g. 09:30-05:00 -> 09:30-17:00, 12:00-08:30 -> 12:00-20:30, 09:00-09:00 -> 09:00-21:00.
  * still close <= open after that: the span cannot be read safely and is dropped (unless allow_overnight, for
    shelters where 20:00-08:00 is a real overnight span).
Any trailing words after the span (e.g. 'Monthly') are kept."""
import re
SPAN = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})(.*)$")
def _m(h, m): return int(h) * 60 + int(m)
def _f(t): return f"{t // 60:02d}:{t % 60:02d}"
def fix_span(s, allow_overnight=False):
    """Returns the corrected span string, or None when it should be dropped. Non-matching text is returned unchanged."""
    m = SPAN.match(s or "")
    if not m: return s
    a, b, rest = _m(m.group(1), m.group(2)), _m(m.group(3), m.group(4)), m.group(5)
    if a == 0 and b == 0: return None
    if allow_overnight and b < a and a >= 17 * 60: return s.strip()  # genuine overnight (evening start)
    if a < 7 * 60 and a < b < 13 * 60: a, b = a + 720, b + 720
    elif b <= a and b < 13 * 60 and b + 720 > a: b += 720
    if b <= a or b > 24 * 60: return None
    return f"{_f(a)} - {_f(b)}{rest}"
def fix_hours(h, allow_overnight=False):
    """dict day -> 'span[ / span]' ; returns (fixed_dict, changes[list of (day, old, new)])."""
    if not isinstance(h, dict): return h, []
    out, ch = {}, []
    for d, v in h.items():
        raw = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", str(v))          # 15.00 -> 15:00
        raw = re.sub(r"(?<![\d:])([01]\d|2[0-3])([0-5]\d)\b", r"\1:\2", raw)   # 1500 -> 15:00
        parts = [p for p in raw.split(" / ") if p.strip().lower() != "closed"]
        parts = [fix_span(p, allow_overnight) for p in parts]
        parts = [p for p in parts if p]
        nv = " / ".join(parts)
        if nv != v: ch.append((d, v, nv or None))
        if nv: out[d] = nv
    return out, ch
def bad_spans(h):
    """Spans whose close is not after the open (for audits/tests)."""
    if not isinstance(h, dict): return []
    r = []
    for d, v in h.items():
        for p in str(v).split(" / "):
            m = SPAN.match(p)
            if m and _m(m.group(3), m.group(4)) <= _m(m.group(1), m.group(2)): r.append((d, p))
    return r
def phone_ok(p):
    """A UK phone we will show must have at least 10 digits; otherwise it is hidden."""
    return len(re.sub(r"\D", "", p or "")) >= 10
