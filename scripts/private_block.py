"""Dean's home address and phone never go on the map (rule 9). Rule 8: the values are not in this repo.

How to set the secret
---------------------
GitHub: Settings → Secrets and variables → Actions → New repository secret.

  Name:  PRIVATE_BLOCKLIST
  Value: one address or phone per line. A vertical bar also separates entries.

Shape only (these are not real; do not put a real address in the repo or in a workflow file):

  1 Example Close, Exampletown EX1 1EX
  01000 000000

The refresh workflows pass it through as:

  env:
    PRIVATE_BLOCKLIST: ${{ secrets.PRIVATE_BLOCKLIST }}

An address entry needs at least 8 characters. A phone entry needs at least 10 digits.
Shorter entries are ignored so a stray character cannot match every listing.

When the secret is unset, there is nothing to compare and publishing continues.
When it is set and a listing contains an entry, that listing is not published and the
publish step exits non-zero (fail closed). The secret text is never copied into a report,
a log line, or the pending list. Logs print match counts only.

Needle rules are the same ones the read-only privacy check uses (scripts/privacy_check.py):
case, spacing, punctuation and postcode spacing, and +44 / 0044 phone forms.
compile_needles(), text_matches() and listing_text() are the shared matcher. The read-only
workflow should import them from here rather than keeping a second copy.
"""
import os, re

def entries(raw=None):
    """Usable blocklist lines from PRIVATE_BLOCKLIST. Empty when the secret is unset."""
    if raw is None:
        raw = os.environ.get('PRIVATE_BLOCKLIST', '')
    if isinstance(raw, (list, tuple)):
        parts = []
        for item in raw:
            parts.extend(re.split(r'[\n|]', item or ''))
    else:
        parts = re.split(r'[\n|]', raw or '')
    return [p.strip() for p in parts if p.strip()]

def _digits(s):
    return re.sub(r'\D', '', s or '')

def _phone_forms(digits):
    """National and +44 / 0044 forms of a UK number, as digit strings."""
    if digits.startswith('0044'):
        digits = '0' + digits[4:]
    elif digits.startswith('44') and len(digits) >= 12:
        digits = '0' + digits[2:]
    forms = {digits}
    if digits.startswith('0'):
        forms |= {'44' + digits[1:], '0044' + digits[1:]}
    return forms

def _squash(s):
    return re.sub(r'[^0-9a-z]', '', (s or '').casefold())

def _spaced(s):
    return re.sub(r'\s+', ' ', (s or '').casefold()).strip()

def compile_needles(raw):
    """Phones and address texts worth comparing. Short entries are dropped."""
    phones, texts = [], []
    for e in entries(raw):
        d = _digits(e)
        has_letters = bool(re.search(r'[a-zA-Z]', e))
        if len(d) >= 10 and not has_letters:
            phones.append(_phone_forms(d))
        elif len(_squash(e)) >= 8:
            texts.append((_spaced(e), _squash(e)))
    return phones, texts

def text_matches(text, needles):
    """True when text contains a compiled entry. Never logs the entry."""
    phones, texts = needles
    if not text:
        return False
    runs = [_digits(m) for m in re.findall(r'[\d+][\d\s().\-+]{8,}\d', text)]
    alld = _digits(text)
    for forms in phones:
        for f in forms:
            if f in alld or any(f in r for r in runs):
                return True
    spaced, squashed = _spaced(text), _squash(text)
    for sp, sq in texts:
        if sp in spaced or sq in squashed:
            return True
    return False

def listing_text(item):
    out = []
    def walk(v):
        if isinstance(v, dict):
            for x in v.values(): walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v: walk(x)
        elif v is not None:
            out.append(str(v))
    walk(item)
    return '\n'.join(out)

def _needles(secrets):
    if secrets is None:
        raw = os.environ.get('PRIVATE_BLOCKLIST', '')
    elif isinstance(secrets, (list, tuple)):
        raw = list(secrets)
    else:
        raw = secrets
    return compile_needles(raw)

def matches(item, secrets=None):
    """True when any usable secret entry appears in this listing. Never logs the secret."""
    phones, texts = _needles(secrets)
    if (not phones and not texts) or not item:
        return False
    return text_matches(listing_text(item), (phones, texts))

def match_count(items, secrets=None):
    """How many listings match. Callers print this count and nothing from the secret."""
    phones, texts = _needles(secrets)
    if (not phones and not texts) or not items:
        return 0
    needles = (phones, texts)
    return sum(1 for i in items if i and text_matches(listing_text(i), needles))

def safe_id(item, secrets=None):
    """The listing id, unless the id itself is what matched. Then nothing identifying is returned."""
    ident = (item or {}).get('id') or ''
    if ident and not matches({'id': ident}, secrets):
        return ident
    return ''
