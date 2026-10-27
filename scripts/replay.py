"""Re-run a decision from the fields already extracted. Page text is refused."""
import json, os
ALLOWED = ("url", "http", "hours_hash", "phones", "access", "ok")
BANNED = ("html", "raw", "text", "body", "page", "content")

def case_from(record):
    """Keep the extracted fields only. A record that carries page text is refused."""
    record = record or {}
    if any(k in record for k in BANNED):
        raise ValueError("page text is not kept")
    return {k: record[k] for k in ALLOWED if k in record}

def cases_from_state(state, limit=500):
    out = []
    for url, site in (state.get("sites") or {}).items():
        if not isinstance(site, dict): continue
        out.append(case_from(dict(site, url=url)))
        if len(out) >= limit: break
    return out

def replay(decision, case):
    """Call decision with the extracted fields only."""
    return decision(case_from(case))

def write(cases, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump({"cases": cases, "stores_html": False}, open(tmp, "w"), indent=0, sort_keys=True)
    os.replace(tmp, path)
