"""Draft inbox for Report a problem emails.

A draft is stored with place_id null and apply false. learning_signals.problem_reports()
does not read this file. Free text never changes a listing, and a place is never matched.
Dean copies a row into overrides/problem_reports.json by hand before it can raise priority.
"""
import json, os

def normalise(row):
    """Keep the text. Force place_id to null and apply to false, whatever was offered."""
    if not isinstance(row, dict): return None
    text = row.get("text") if isinstance(row.get("text"), str) else None
    if text is None and isinstance(row.get("what"), str): text = row.get("what")
    if not isinstance(text, str) or not text.strip(): return None
    when = row.get("when") if isinstance(row.get("when"), str) else None
    return {"when": when, "text": text.strip(), "place_id": None, "apply": False}

def load(path):
    try: raw = json.load(open(path, encoding="utf-8"))
    except Exception: return []
    rows = raw.get("drafts") if isinstance(raw, dict) else raw
    if not isinstance(rows, list): return []
    return [r for r in (normalise(x) for x in rows) if r]

def save(path, rows):
    """Write drafts only. apply stays false and place_id stays null. Listings are not touched."""
    clean = []
    for row in rows or []:
        item = normalise(row)
        if not item: continue
        item["place_id"] = None
        item["apply"] = False
        clean.append(item)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    body = {"apply": False, "drafts": clean}
    tmp = path + ".tmp"
    json.dump(body, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return body

def note(path):
    rows = load(path)
    if not rows: return "no problem-report drafts - no effect"
    return "%d problem-report drafts are waiting for Dean. They are not applied and do not change a listing." % len(rows)
