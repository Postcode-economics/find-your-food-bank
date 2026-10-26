"""Phone label and council-switchboard rules (Dean, rules 21 and 5).

A card's phone label comes from the source page when the page names a role next to the
number (for example Pastor). overrides/phone_labels.json is only the fallback.
When the page says not to phone, the number is held and not published.

A council switchboard, main number, or customer-services line is not the venue's phone.
A council out-of-hours line is kept only when the council page names it as that line
and the record is labelled (council_label plus the council page URL).
"""
import re

ROLE = re.compile(
    r'\b(pastor|minister|reverend|vicar|manager|co-?ordinator|coordinator|reception|'
    r'duty manager|warden|referral line|church office|head office|project manager|'
    r'volunteer co-?ordinator|organiser|organizer)\b', re.I)
NO_CALL = re.compile(
    r"\b(?:no phone calls|do not phone|don't phone|do not call|don't call|please do not call|"
    r"calls are not accepted|unable to take calls|we cannot take calls|no telephone)\b", re.I)
SWITCH_NEAR = re.compile(
    r'switchboard|main (?:council )?number|customer services|general enquiries', re.I)
OOH_NEAR = re.compile(r'out[- ]of[- ]hours|outside office hours|homeless', re.I)
SWITCH_LABEL = re.compile(r'switchboard|main number|customer services|general enquiries', re.I)
OOH_LABEL = re.compile(r'out[- ]of[- ]hours|homeless', re.I)


def _tidy(role):
    low = (role or '').strip().lower()
    special = {
        'referral line': 'Referral line',
        'church office': 'Church office',
        'head office': 'Head office',
        'duty manager': 'Duty manager',
        'project manager': 'Project manager',
        'volunteer co-ordinator': 'Volunteer co-ordinator',
        'volunteer coordinator': 'Volunteer coordinator',
    }
    if low in special:
        return special[low]
    return ' '.join(w[:1].upper() + w[1:] for w in low.split())


def calls_forbidden(text):
    """True when the page tells people not to phone."""
    return bool(text and NO_CALL.search(text))


def label_from_page(text, number=None):
    """Role named next to the number, or None when the page does not name one."""
    if not text:
        return None
    lines = text.splitlines() or [text]
    chunks = []
    digits = re.sub(r'\D', '', number or '')
    if len(digits) >= 10:
        tail = digits[-10:]
        for i, line in enumerate(lines):
            if tail in re.sub(r'\D', '', line):
                prev = lines[i - 1] if i else ''
                chunks.append((prev + ' ' + line).strip())
        if not chunks:
            return None
    else:
        chunks = lines
    for chunk in chunks:
        m = ROLE.search(chunk)
        if m:
            return _tidy(m.group(1))
    return None


def labelled_council_ooh(item):
    """True when this record's council line is labelled and points at the council page.

    The label has to name an out-of-hours or homeless line. A switchboard or
    'main number' label does not count, and a council phone with no label does not count.
    """
    if not item:
        return False
    label = item.get('council_label') or ''
    phone = item.get('council_ooh') or item.get('council_phone')
    url = item.get('council_url') or ''
    if not (label and phone and url):
        return False
    if SWITCH_LABEL.search(label):
        return False
    return bool(OOH_LABEL.search(label))


def _windows(text, number, radius=90):
    d = re.sub(r'\D', '', number or '')
    if len(d) < 10 or not text:
        return []
    d = d[-10:]
    pat = re.compile(r'\D*'.join(d))
    out = []
    for m in pat.finditer(text):
        a = max(0, m.start() - radius)
        b = min(len(text), m.end() + radius)
        out.append(text[a:b])
    return out


def switchboard_blocked(number, text, item=None):
    """True when this number must not be published as the venue phone.

    Allowed only when the text next to the number names it as the council
    out-of-hours / homeless line AND the record is labelled with the council page.
    """
    windows = _windows(text or '', number)
    if not windows and text and SWITCH_NEAR.search(text):
        digits = re.sub(r'\D', '', number or '')
        if len(digits) >= 10 and digits[-10:] in re.sub(r'\D', '', text):
            windows = [text]
    if not windows:
        return False
    hit = any(SWITCH_NEAR.search(w) for w in windows)
    named = any(OOH_NEAR.search(w) for w in windows)
    if not hit:
        return False
    if named and labelled_council_ooh(item or {}):
        return False
    return True


def apply_contact_label(item, override=None, page_text=None):
    """Set phone_label from the page when it names a role, else from the override.

    Returns 'held', 'page', 'override', or None. A held number is cleared so it
    is not published. The number itself is not returned.
    """
    if page_text and calls_forbidden(page_text) and (item.get('phone') or item.get('tel')):
        item['phone'] = ''
        item['tel'] = ''
        item.pop('phone_label', None)
        item['phone_held_reason'] = 'page says no phone calls'
        return 'held'
    label = label_from_page(page_text, item.get('phone') or item.get('tel')) if page_text else None
    src = 'page' if label else None
    if not label and isinstance(override, str) and override.strip():
        label = override.strip()
        src = 'override'
    if label and (item.get('phone') or item.get('tel')):
        item['phone_label'] = label
        return src
    return None
