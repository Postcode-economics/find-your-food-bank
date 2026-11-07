"""Per-listing checked dates; never use a layer stamp as a new check.

Only generated records are changed. Human overlay verification and all other
card facts are left alone. A successful check need not change any other fact.
"""
import datetime
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
FIELDS = ("verified_on", "checked_on", "hours_checked", "last_verified")


def uk_day(value=None):
    if value is None:
        value = datetime.datetime.now(datetime.timezone.utc)
    if isinstance(value, str):
        try:
            value = (datetime.date.fromisoformat(value) if len(value) == 10 else
                     datetime.datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return ""
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return ""  # an unzoned timestamp is not evidence of a UK check day
        return value.astimezone(UK).date().isoformat()
    return value.isoformat() if isinstance(value, datetime.date) else ""


def latest(record):
    values = [uk_day(record.get(k, "")) for k in FIELDS]
    ot = record.get("opening_times")
    if isinstance(ot, dict):
        values.append(uk_day(ot.get("checked_date", "")))
    values.append(uk_day(record.get("checked", "")))
    # Match the existing card precedence; a feed-generated last_verified must
    # not override an explicit earlier verification on a failed check.
    return next((v for v in values if v), "")


def preserve(item, *records):
    """Carry an existing check (including a newer human check), never fabricate one."""
    day = max([latest(item)] + [latest(r) for r in records if isinstance(r, dict)])
    if day:
        item["verified_on"] = day


def success(item, checked_at=None):
    """Call only after THIS listing's live check succeeds, not when it is kept."""
    day = uk_day(checked_at)
    if day:
        preserve(item, {"verified_on": day})


def preserve_foodbanks(items, previous, fetched=""):
    """Retain the date previously displayed, including the existing GF-only fallback."""
    previous = {i["id"]: i for i in previous}
    for item in items:
        old = previous.get(item["id"], {})
        preserve(item, old)
        if not latest(item) and old.get("givefood"):
            preserve(item, {"verified_on": fetched})
