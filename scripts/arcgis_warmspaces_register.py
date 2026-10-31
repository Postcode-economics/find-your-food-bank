"""Register council ArcGIS warm-space feeds in overrides (verified + Dean approval).

Run after adding feeds to overrides/arcgis_warmspaces.json. Does not overwrite existing
verified phone or council fields. Lancashire feed phones are copied when OrgContactShare allows.
Other feeds: optional venue-page phone lookup (see --phones).
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arcgis_warmspaces as A
import phone_rule
from common import get, load_js, today

VER_PATH = os.path.join(ROOT, "overrides", "warmspaces_verified.json")
APPROVED_PATH = os.path.join(ROOT, "overrides", "approved_new_places.json")
WS_PATH = os.path.join(ROOT, "warmspaces.js")
PHONE_RE = phone_rule.PHONE_RE


def _load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def _name_hits(text, name):
    words = [w for w in re.findall(r"[a-z]{4,}", (name or "").lower())
             if w not in ("church", "centre", "center", "community", "library", "warm", "welcome", "hall")]
    low = (text or "").lower()
    return (not words) or sum(1 for w in words if w in low) >= min(2, len(words))


def phone_from_page(url, name, postcode):
    if not url or not url.startswith("http"):
        return None
    try:
        import recheck
        page = recheck.fetch(url)
    except Exception:
        return None
    if page.get("http") != 200 or len(page.get("text") or "") < 200:
        return None
    t = page["text"]
    pc = re.sub(r"[^A-Z0-9]", "", (postcode or "").upper())
    if pc and pc not in t.upper().replace(" ", ""):
        if not _name_hits(t, name):
            return None
    elif not _name_hits(t, name):
        return None
    for m in PHONE_RE.finditer(t):
        raw = m.group(0).strip()
        if phone_rule.is_dean(raw):
            continue
        d = phone_rule.digits(raw)
        if len(d) < 10:
            continue
        return {"phone": raw, "phone_source": page.get("final_url") or url, "phone_quote": raw}
    return None


def register(run_day, feed_ids=None, lookup_phones=False, dry_run=False):
    verified = _load_json(VER_PATH, {})
    approved = _load_json(APPROVED_PATH, {"foodbanks": {}, "shelters": {}, "warmspaces": {}})
    approved.setdefault("warmspaces", {})
    live = {x["id"]: x for x in load_js(WS_PATH, "WARMSPACES").get("items", [])}
    existing = [{"id": x["id"], "name": x["name"], "postcode": x["postcode"]} for x in live.values()]
    stats = {}
    for feed in A.load_config():
        fid = feed.get("id")
        if feed_ids and fid not in feed_ids:
            continue
        records, skipped = A.read_feed(feed, get, run_day, existing)
        for rec in records:
            existing.append({"id": rec["id"], "name": rec["name"], "postcode": rec["postcode"]})
        dupes = [s for s in skipped if "duplicate" in (s.get("reason") or "")]
        held = []
        published_ids = []
        for rec in records:
            eid = rec["id"]
            ev = A.evidence(rec, feed)
            note = A.approval_note(feed, run_day).replace(
                feed.get("council") or "", "%s warm-space feed" % (feed.get("council") or feed.get("source"))
            )
            if "warm-space feed warm-space feed" in note:
                note = A.approval_note(feed, run_day)
            note = note.replace(
                "%s warm-space feed, checked" % (feed.get("council") or "Council"),
                "%s warm-space feed, checked" % (feed.get("council") or feed.get("source") or "Council"),
            )
            short = "%s warm-space feed, checked %s." % (feed.get("council") or feed.get("source"), run_day)
            note = ("Dean blanket approval 30 Oct 2026 for verified places from their own official source; "
                    + short)
            cur = verified.get(eid, {})
            merged = dict(cur)
            merged.update({k: v for k, v in ev.items() if v})
            merged["name"] = rec["name"]
            if not merged.get("verified_on"):
                merged["verified_on"] = run_day
            if rec.get("_feed_phone") and not merged.get("phone"):
                merged["phone"] = rec["_feed_phone"]
                merged["phone_source"] = rec.get("_feed_phone_source") or feed.get("url")
                merged["phone_quote"] = rec["_feed_phone"]
            elif lookup_phones and not merged.get("phone"):
                page = rec.get("_venue_page") or rec.get("website") or ""
                if page.startswith("http") and "warmwelcome" not in page.lower():
                    got = phone_from_page(page, rec["name"], rec["postcode"])
                    if got:
                        merged.update(got)
            if not merged.get("phone"):
                held.append({"id": eid, "name": rec["name"], "postcode": rec["postcode"], "reason": "no verified phone"})
            if not dry_run:
                verified[eid] = merged
                if eid not in live:
                    approved["warmspaces"][eid] = note
            published_ids.append(eid)
        stats[fid] = {
            "records_in_feed": len(records) + len(skipped) - len(dupes),
            "approved_filter_kept": len(records) + len(dupes),
            "parsed": len(records) + len(dupes),
            "duplicates": len(dupes),
            "registered": len(records),
            "held_no_phone": len(held),
            "held": held,
            "skipped": [s for s in skipped if "duplicate" not in (s.get("reason") or "")],
        }
    if not dry_run:
        _save_json(VER_PATH, verified)
        _save_json(APPROVED_PATH, approved)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=today())
    ap.add_argument("--feeds", nargs="*", help="feed ids (default: all except brighton-hove)")
    ap.add_argument("--phones", action="store_true", help="look up phones on venue pages when missing")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    feed_ids = args.feeds
    if not feed_ids:
        feed_ids = [f["id"] for f in A.load_config() if f["id"] != "brighton-hove"]
    stats = register(args.day, feed_ids=feed_ids, lookup_phones=args.phones, dry_run=args.dry_run)
    print(json.dumps(stats, indent=2)[:120000])


if __name__ == "__main__":
    main()
