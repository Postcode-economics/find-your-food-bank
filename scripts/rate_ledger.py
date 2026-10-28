"""Count calls to the hosts we pay attention to, and pause a host for the rest of this run after HTTP 429.

A paused host is skipped until the next run that was already scheduled. The place is not dropped
and the weekly floor is not changed. Nothing here edits a cron line.
"""
import json, os, urllib.parse
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PATH = os.path.join(ROOT, "reports", "rate_ledger.json")

def host_of(url):
    h = urllib.parse.urlparse(url or "").netloc.lower().removeprefix("www.")
    if "postcodes.io" in h: return "postcodes.io"
    if "naturalresources.wales" in h: return "naturalresources.wales"
    if "metoffice.gov.uk" in h: return "metoffice.gov.uk"
    if "facebook.com" in h: return "facebook.com"
    return h or "unknown"

class Ledger:
    def __init__(self):
        self.counts, self.paused = {}, set()
    def allow(self, url):
        return host_of(url) not in self.paused
    def record(self, url, http=None):
        h = host_of(url)
        self.counts[h] = self.counts.get(h, 0) + 1
        try:
            if int(http) == 429: self.paused.add(h)
        except (TypeError, ValueError): pass
        return h not in self.paused
    def note(self):
        if not self.counts: return "no calls recorded - no effect"
        bits = ", ".join("%s %d" % (h, n) for h, n in sorted(self.counts.items()))
        paused = ", ".join(sorted(self.paused)) or "none"
        return "calls: %s. paused for the rest of this run after HTTP 429: %s. They stay due for a later scheduled run." % (bits, paused)

LEDGER = Ledger()

def save(path=None, day=None):
    """Merge this process into the day's file. A new day replaces the previous day. Places are not touched."""
    path = path or PATH
    try: cur = json.load(open(path))
    except Exception: cur = {}
    if not isinstance(cur, dict) or cur.get("day") != day:
        cur = {"day": day, "counts": {}, "paused": []}
    counts = dict(cur.get("counts") or {})
    for h, n in LEDGER.counts.items(): counts[h] = int(counts.get(h) or 0) + int(n)
    paused = sorted(set(cur.get("paused") or []) | set(LEDGER.paused))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump({"day": day, "counts": counts, "paused": paused}, open(tmp, "w"), indent=0, sort_keys=True)
    os.replace(tmp, path)
    return counts

def note_from(obj):
    if not isinstance(obj, dict) or not obj.get("counts"): return "no calls recorded - no effect"
    bits = ", ".join("%s %d" % (h, n) for h, n in sorted(obj["counts"].items()))
    paused = ", ".join(obj.get("paused") or []) or "none"
    return "calls: %s. paused after HTTP 429: %s" % (bits, paused)
