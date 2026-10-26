"""Once a year, ask Dean to re-read source terms. This adds no URLs.

The note was written on 25 October 2026, so that day is not a reminder.
The first reminder is on or after 25 October 2027, and then once each year.
"""
import datetime, json, os

WRITTEN = datetime.date(2026, 10, 25)
LINE = ("Please re-read the terms for Give Food, IFAN, council pages, the Met Office "
        "and Natural Resources Wales. This reminder adds no URLs.")

def _day(value):
    if isinstance(value, datetime.datetime): return value.date()
    if isinstance(value, datetime.date): return value
    return datetime.date.fromisoformat(str(value)[:10])

def due(today, last, written=WRITTEN):
    """True on or after the anniversary, once a year. The day the note was written is not a reminder."""
    today = _day(today)
    if today <= written: return False
    first = datetime.date(written.year + 1, written.month, written.day)
    if today < first: return False
    ann = datetime.date(today.year, written.month, written.day)
    if today < ann: return False
    if last:
        try: prev = _day(last)
        except Exception: prev = None
        if prev and prev.year == today.year and prev >= ann: return False
    return True

def reminder(today, state=None):
    state = state if isinstance(state, dict) else {}
    if not due(today, state.get("last")): return None
    return {"last": _day(today).isoformat(), "line": LINE, "urls": []}

def load(path):
    try: state = json.load(open(path, encoding="utf-8"))
    except Exception: state = {}
    return state if isinstance(state, dict) else {}

def consider(today, path):
    """Store the reminder date when one is due. A quiet day writes nothing. No URLs are added."""
    row = reminder(today, load(path))
    if not row: return None
    if row.get("urls"): raise RuntimeError("the reminder must not add URLs")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    json.dump({"last": row["last"]}, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, path)
    return row
