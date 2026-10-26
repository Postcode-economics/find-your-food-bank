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


# ---- phone clean-up (every refresh, all layers) ----
# Source phones can hold two numbers ("01278445682or01278422568", "01483506763%2F01483575128",
# "01933653346%2F652986"), HTML left over from scraping ('02088711812"target="_blank"...'),
# a dropped leading 0 ("1984623991") or a mistyped number. tel: links must only ever get ONE valid UK number.
import html as _html
from urllib.parse import unquote as _unquote

# Ofcom "mixed" areas where some local numbers have 5 digits (10-digit national number), e.g. 01460 57811
FIVE_DIGIT_AREAS = set("01204 01208 01254 01276 01297 01298 01363 01364 01384 01386 01404 01420 01460 01461 01480 01488 01524 01527 01562 01566 01606 01629 01635 01647 01659 01695 01726 01744 01750 01768 01827 01837 01884 01900 01905 01935 01949 01963 01995".split())

def _valid_uk(d):
    """UK number in national format: 11 digits starting 01/02/03/05/07/08/09, or the 10-digit 016977 / 0800 1111 cases."""
    if re.fullmatch(r"0[1235789]\d{9}", d): return True
    if len(d) == 10 and d[:5] in FIVE_DIGIT_AREAS: return True
    return bool(re.fullmatch(r"016977\d{4}|08001111", d))

def _fmt_uk(d):
    if re.match(r"02", d): return "%s %s %s" % (d[:3], d[3:7], d[7:])
    if re.match(r"01\d1|011", d): return "%s %s %s" % (d[:4], d[4:7], d[7:])
    if re.match(r"0[3589]", d): return "%s %s %s" % (d[:4], d[4:7], d[7:])
    return "%s %s" % (d[:5], d[5:])  # also 10-digit 01xxx xxxxx

def clean_phone(p):
    """Return (display, tel). tel = first valid UK number (digits only) or ''; display lists every valid number
    joined by ' or ' (only the first is linked). Invalid parts are dropped; nothing valid -> ('', '')."""
    s = _html.unescape(_unquote(str(p or "")))
    s = re.split(r"[\"<>]|\btarget=|\bhref=", s)[0]  # HTML junk after the number
    s = re.sub(r"\(\s*0\s*\)", "", s)  # +44 (0)1234 ...
    parts = re.split(r"\s*(?:\bor\b|\band\b|or(?=\d)|(?<=\d)or|and(?=\d)|(?<=\d)and|/|,|;|&|\|)\s*", s, flags=re.I)
    out = []
    for part in parts:
        d = re.sub(r"[^\d+]", "", part)
        if d.startswith("+44"): d = "0" + d[3:]
        elif d.startswith("0044"): d = "0" + d[4:]
        d = d.replace("+", "")
        if not d: continue
        if out and 3 <= len(d) <= 7 and d[0] != "0":  # "01933653346/652986": shorthand for same area code
            d = out[0][:len(out[0]) - len(d)] + d
        elif len(d) == 10 and d[0] in "1237":  # leading 0 dropped
            d = "0" + d
        if _valid_uk(d) and d not in out: out.append(d)
    if not out: return "", ""
    return " or ".join(_fmt_uk(d) for d in out), out[0]

def apply_phone(x, key="phone", page_text=None):
    """In place: x[key] -> cleaned display text, x['tel'] -> the one number the Call button dials.

    A council switchboard is cleared unless the council page names it as the out-of-hours line
    and the record is labelled (rule 5). page_text is the source page when the caller has it.
    """
    if not x.get(key): x["tel"] = ""; return x
    raw_text = str(x.get(key) or "")
    disp, tel = clean_phone(raw_text)
    raw = re.sub(r"[^\d+]", "", raw_text).replace("+44", "0", 1)
    if tel and " or " not in disp and raw == tel and not re.search(r"[A-Za-z%<>\"&;/]", raw_text): disp = raw_text.strip()  # already one clean number: keep its own wording
    x[key], x["tel"] = disp, tel
    import phone_rules
    blob = " ".join(p for p in (raw_text, page_text or "") if p)
    if tel and phone_rules.switchboard_blocked(tel, blob, x):
        x[key], x["tel"] = "", ""
        x["phone_held_reason"] = "council switchboard"
    return x
