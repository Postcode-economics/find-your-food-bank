"""Version stamp for the canonical food-bank file (data.full.js).

The browser file data.js is still built by compact.py with the same fields as before.
A missing stamp is the previous version, so files written before this stamp still load.
Readers accept the current version and the one before it. They do not guess a newer one.
"""
CURRENT = 1

def accepts(version, current=CURRENT):
    """True for the current stamp and the one before. A missing stamp is the previous version."""
    if version is None: version = current - 1
    try: version = int(version)
    except (TypeError, ValueError): return False
    return version in (current, current - 1)

def stamp(meta, current=CURRENT):
    """Copy of a payload with schema_version set. Items are left as they were given."""
    out = dict(meta or {})
    out["schema_version"] = current
    return out
