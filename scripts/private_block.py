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
a log line, or the pending list.
"""
import json, os, re

def entries(raw=None):
    """Usable blocklist entries from PRIVATE_BLOCKLIST. Empty when the secret is unset."""
    if raw is None:
        raw = os.environ.get('PRIVATE_BLOCKLIST', '')
    out = []
    for part in re.split(r'[\n|]', raw or ''):
        s = part.strip()
        if s:
            out.append(s)
    return out

def _text(s):
    return re.sub(r'\s+', ' ', (s or '').casefold())

def _usable_phone(s):
    digits = re.sub(r'\D', '', s or '')
    letters = re.sub(r'[\d\W_]+', '', s or '')
    return digits if len(digits) >= 10 and not letters else ''

def matches(item, secrets=None):
    """True when any usable secret entry appears in this listing. Never logs the secret."""
    secrets = entries() if secrets is None else (secrets or [])
    if not secrets or not item:
        return False
    blob = _text(json.dumps(item, ensure_ascii=False, default=str))
    digits = re.sub(r'\D', '', blob)
    for s in secrets:
        phone = _usable_phone(s)
        if phone and phone in digits:
            return True
        text = _text(s)
        if len(text) >= 8 and text in blob:
            return True
    return False

def safe_id(item, secrets=None):
    """The listing id, unless the id itself is what matched. Then nothing identifying is returned."""
    secrets = entries() if secrets is None else (secrets or [])
    ident = (item or {}).get('id') or ''
    if ident and not matches({'id': ident}, secrets):
        return ident
    return ''
