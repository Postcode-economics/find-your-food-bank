"""Normalise scraped opening-time strings into a clean Mon-Sun table.
raw strings mix the food bank's own prose ('Tuesdays 10.30am - 2.30pm') with the
Trussell locations table ('Mon Closed Tue 10:30 - 14:30'), often duplicated.
normalise(ot) returns a new dict:
  status TIMES_FOUND + structured {day:[[HH:MM,HH:MM]]} when every segment parses and agrees,
  otherwise status TIMES_TEXT_ONLY + lines [deduped segments] (shown once, 'as written'),
  or None when the text is only a blank Trussell placeholder (every day Closed).
Conservative: any unrecognised word, monthly/fortnightly wording, or two segments giving the
same day different times -> text fallback, never a guessed table."""
import re
DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
DAYRX = r'(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*'
DASH = r'\s*(?:-|–|—|to|until|till|through|thru)\s*'
T = r'(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?|midday|noon|midnight)'
FILL = {'from', 'and', 'or', 'the', 'open', 'opening', 'times', 'time', 'on', 'between', 'each', 'every', 'are', 'is', 'we', 'hours', 's', 'including', 'at'}

def _day(tok): return DAYS.index(tok[:3])

def _t(s):
    s = s.strip().lower().replace('a.m.', 'am').replace('p.m.', 'pm').replace(' ', '')
    if s in ('midday', 'noon'): return 12, 0, 'pm'
    if s == 'midnight': return 0, 0, 'am'
    m = re.fullmatch(r'(\d{1,2})(?:[:.](\d{2}))?(am|pm)?', s)
    if not m: return None
    return int(m.group(1)), int(m.group(2) or 0), m.group(3)

def _to24(h, mi, ap):
    if ap == 'pm' and h < 12: h += 12
    if ap == 'am' and h == 12: h = 0
    return h * 60 + mi

def _range(a, b):
    a, b = _t(a), _t(b)
    if not a or not b: return None
    (h1, m1, p1), (h2, m2, p2) = a, b
    if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59 or (h1, m1) == (h2, m2): return None
    if h1 > 12 or h2 > 12 or (p1 is None and p2 is None and (h1 == 0 or h2 == 0)): p1 = p1 or ('pm' if h1 >= 12 else None); p2 = p2 or ('pm' if h2 >= 12 else None)
    if p2 is None and p1 is None:   # e.g. '10 - 12.30', '1.30-3.30', '12.00 - 2.00'
        if h1 > 12 or h2 > 12: s, e = h1 * 60 + m1, h2 * 60 + m2
        else:
            s = _to24(h1, m1, 'pm' if h1 < 7 else ('pm' if h1 == 12 else 'am'))
            e = _to24(h2, m2, 'am' if (h2 > h1 and h2 < 12 and h1 >= 7) else 'pm')
            if h2 == 12: e = 12 * 60 + m2
    else:
        e = _to24(h2, m2, p2) if p2 or h2 > 12 else None
        if p1 or h1 > 12: s = _to24(h1, m1, p1)
        else:  # start has no am/pm: same half as end unless that makes it later than the end
            s = _to24(h1, m1, p2) if p2 else None
            if s is not None and e is not None and s >= e: s = _to24(h1, m1, 'am')
        if e is None: e = _to24(h2, m2, 'pm' if _to24(h2, m2, 'am') <= s else 'am')
    if not (6 * 60 <= s < e <= 23 * 60 + 30) or e - s > 13 * 60: return None
    return '%02d:%02d' % divmod(s, 60), '%02d:%02d' % divmod(e, 60)

def _days(spec):
    """'Monday, Tuesday & Friday' / 'Mon - Thurs' / 'Monday-Friday' -> list of day idx, or None"""
    full = re.findall(r'(mon|tue|wed|thu|fri|sat|sun)[a-z]*|(-|–|—|\bto\b|\bthrough\b|\bthru\b)|(,|&|/|\band\b|\bor\b)|(\S+)', spec)
    out, pend = [], False
    for d, dash, sep, junk in full:
        if junk: return None
        if d:
            i = _day(d)
            if pend and out:
                a = out[-1]
                if i <= a: return None
                out += list(range(a + 1, i + 1)); pend = False
            else: out.append(i)
        elif dash: pend = True
    return out if out and not pend else None

def parse_segment(seg):
    """-> dict day -> list of ranges ([] = explicitly closed), or None if not fully understood"""
    s = seg.lower().replace('\u00a0', ' ')
    if re.search(r'month|fortnight|alternat|other|except|week|\b(1st|2nd|3rd|4th|first|second|third|fourth|last)\b|only|donat|appoint|referr|age|term|holiday|evening|morning|afternoon|lunch|by\b|via', s): return None
    s = re.sub(r'^opening times\s*', '', s).strip()
    if re.search(r'[-–—]\s*[-–—]', s): return None  # 'Thursday – – – Friday': a blank cell on their site, don't guess
    # chunks: <dayspec> <sep>? (Closed | time range [, time range])
    rx = re.compile(r'((?:' + DAYRX + r'[\s,&/\-–—]*(?:(?:and|or|to|through|thru)\s+)?)+)[\s:\-–—,]*(?:from\s+)?(closed|' + T + DASH + T + r'(?:\s*(?:,|and|&)\s*' + T + DASH + T + r')?)', re.I)
    res, pos = {}, 0
    for m in rx.finditer(s):
        gap = s[pos:m.start()]
        if re.sub(r'[\s,;:|.\-–—()]+|\b(' + '|'.join(FILL) + r')\b', '', gap): return None
        pos = m.end()
        days = _days(re.sub(r'\b(from|s)\b', ' ', m.group(1)).strip(' ,:-–—'))
        if days is None: return None
        if m.group(2) == 'closed': rng = []
        else:
            r1 = _range(m.group(3), m.group(4))
            if not r1: return None
            rng = [list(r1)]
            if m.group(5):
                r2 = _range(m.group(5), m.group(6))
                if not r2: return None
                rng.append(list(r2))
        for d in days:
            if d in res and res[d] != rng and rng:
                if res[d] == []: return None
                res[d] = sorted(res[d] + [r for r in rng if r not in res[d]])
            elif d not in res: res[d] = rng
    if pos == 0 or re.sub(r'[\s,;:|.\-–—()]+|\b(' + '|'.join(FILL) + r')\b', '', s[pos:]): return None
    return res

JUNK = re.compile(r'shop|caf[eé]|worship|school|quiz|market|conference|alpha|\bkids\b|youth|talks|\b(00:00|(\d\d:\d\d)\s*[-–]\s*\2)\b', re.I)

def _segments(raw):
    seen, out = set(), []
    for p in (raw or '').split('|'):
        p = re.sub(r'\s+', ' ', p).strip(' ;,')
        p = re.split(r'\s+Address\b', p)[0].strip(' ;,')   # scraped table ran on into the address block
        p = re.sub(r'\b(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*:?\s+(\d\d:\d\d)\s*[-–]\s*\1\b', ' ', p, flags=re.I).strip()  # drop broken 'Mon 00:00 - 00:00' cells, keep the rest of the row
        if JUNK.search(p): continue   # not food bank times (charity shop, café, church events, broken 10:00-10:00 rows)
        k = re.sub(r'[^a-z0-9]', '', p.lower())
        if p and k not in seen: seen.add(k); out.append(p)
    return out

def _pretty(seg, parsed):
    """human version of a segment for the text fallback (Trussell table rows -> 'Tue 10:30–14:30')"""
    if parsed is not None and re.match(r'^(opening times\s*)?(mon|tue|wed|thu|fri|sat|sun) (closed|\d)', seg, re.I):
        open_ = [(d, r) for d, r in sorted(parsed.items()) if r]
        if open_: return ', '.join('%s %s' % (DAYS[d].title(), ', '.join('–'.join(x) for x in r)) for d, r in open_)
    return seg

def normalise(ot):
    if not ot or not ot.get('raw') or ot.get('status') != 'TIMES_TEXT_ONLY': return ot
    out = dict(ot); segs = _segments(ot['raw'])
    parsed = [parse_segment(x) for x in segs]
    merged, ok = {}, all(p is not None for p in parsed)
    if ok:
        for p in parsed:
            for d, r in p.items():
                if d in merged and merged[d] != r: ok = False
                merged[d] = r
    if not segs or (ok and not any(merged.values())):
        return None  # blank Trussell placeholder: every day 'Closed' -> times not listed
    if ok:
        out['status'] = 'TIMES_FOUND'; out['parsed_from_text'] = True
        out['structured'] = {DAYS[d]: r for d, r in sorted(merged.items()) if r}
        return out
    lines, seen = [], set()
    for x, p in zip(segs, parsed):
        if p is not None and not any(p.values()): continue   # a row that only says 'Closed'
        y = _pretty(x, p)
        if y not in seen: seen.add(y); lines.append(y)
    if not lines: return None
    out['lines'] = lines
    return out
