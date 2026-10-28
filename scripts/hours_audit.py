"""Re-read every food-bank card that has a source URL and compare the open days with that page.

The 3x-daily refresh used to treat a card as confirmed when each stored clock time occurred somewhere
on the site. A Friday-only card therefore stayed confirmed while the same page also listed Monday and
Wednesday. This audit uses the per-postcode timetable (discover.extract_times) instead.

Rule 27 (26 Oct 2026): the only page that counts is the live one. This script does not read a saved,
cached, or archived copy. If the live page does not open, the card is unclear and is left unchanged.

Unambiguous: one timetable for this postcode, not office-like, not delivery-only, not a donation block,
not hand-reviewed, and not the same wording copied onto several postcodes. Those are listed as clear mismatches.
This audit writes no hours: the only hours-apply path is discover.times_gate_apply / times_finder.decide (2 identical
runs, logged with an undo in reports/times_auto_applied.json, scripts/times_revert.py). Hours are never invented.

Run as four equal shards (`--shard N --shards 4`), then `--merge`. One request at a time to a domain.
"""
import csv, fcntl, json, os, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discover
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
UA = "Mozilla/5.0 (helpmap.uk times reader; hello@helpmap.uk)"
GAP = 2.0  # one live request at a time per domain, then this pause, across every shard
LOCK_DIR = "/tmp/helpmap-live-domain-locks"  # timestamps only, so shards share the pause; never a page body
COLS = ["id", "name", "postcode", "source_url", "shown_days", "source_days", "missing_days", "extra_days",
        "shown_hours", "source_hours", "evidence", "decision", "note"]

def load_full():
    p = os.path.join(ROOT, "data.full.js")
    s = open(p, encoding="utf-8").read()
    return json.loads(s[s.index("=") + 1:].strip().rstrip(";"))

def hours_text(table):
    bits = []
    for d in ORDER:
        if table.get(d):
            bits.append(d + " " + ", ".join("%s-%s" % (a, b) for a, b in table[d]))
    return "; ".join(bits)

def day_list(table):
    return [d for d in ORDER if table.get(d)]

def visible_table(item):
    """Days the card prints. A donations-only pin prints no opening times."""
    if item.get("kind") in ("warehouse", "dropoff"):
        return {}
    return discover.shown_table(item.get("opening_times")) or {}

def stored_table(item):
    return discover.shown_table(item.get("opening_times")) or {}

def _snip(text, needle):
    t = text or ""
    n = (needle or "").upper().replace(" ", "")
    up = t.upper().replace(" ", "")
    i = up.find(n) if n else -1
    if i < 0:
        i = t.lower().find((needle or "")[:16].lower())
    if i < 0:
        return " ".join(t.split())[:300]
    # map the no-space index back approximately by walking
    raw_i = 0
    seen = 0
    target = i if n and up.find(n) == i else 0
    if n and up.find(n) >= 0:
        for raw_i, ch in enumerate(t):
            if ch != " ":
                seen += 1
            if seen >= i + 1:
                break
    else:
        raw_i = max(i, 0)
    return " ".join(t[max(0, raw_i - 80):raw_i + 220].split())

def judge_card(item, text, protected=False):
    """One source page, already plain text. -> row dict, or None when nothing differs and nothing is doubtful."""
    ot = item.get("opening_times") or {}
    text = text or ""
    extracted = discover.extract_times(text, item.get("postcode")) if text else None
    role = discover.centre_role(text, item.get("postcode")) if text else None
    shown = visible_table(item)
    clear = extracted and extracted.get("status") == "TIMES_FOUND" and extracted.get("structured")
    source = {k: v for k, v in (extracted.get("structured") or {}).items() if v} if clear else {}
    sd, od = day_list(shown), day_list(source)
    missing = [d for d in od if d not in sd]
    extra = [d for d in sd if d not in od]
    differ = bool(clear and (missing or extra or hours_text(shown) != hours_text(source)))
    delivery_note = role == "delivery" or (not clear and discover.DELIVERY_ROLE.search(_near(text, item.get("name") or "")))
    row = {"id": item.get("id"), "name": item.get("name") or "", "postcode": item.get("postcode") or "",
           "source_url": ot.get("source_url") or "", "shown_days": "|".join(sd), "source_days": "|".join(od),
           "missing_days": "|".join(missing), "extra_days": "|".join(extra), "shown_hours": hours_text(shown),
           "source_hours": hours_text(source), "evidence": "", "decision": "", "note": "",
           "structured": source, "raw": (extracted or {}).get("raw") or "", "role": role or ""}
    if not clear:
        if delivery_note:
            row.update(decision="review", evidence=_snip(text, item.get("postcode") or item.get("name")),
                       note="source says delivery only or not open to the public; hours left unchanged")
            return row
        return None
    row["evidence"] = (extracted.get("raw") or "")[:400]
    if discover.office_like(source):
        if not differ: return None
        row.update(decision="review", note="timetable looks like office hours; not applied")
        return row
    if role == "delivery" or role == "donation":
        row.update(decision="review", note="source says %s, not a walk-in collection timetable; not applied" % role)
        return row
    if protected:
        if not differ: return None
        row.update(decision="review", note="hand-reviewed hours; left unchanged")
        return row
    hidden_warehouse = item.get("type") == "foodbank" and item.get("kind") in ("warehouse", "dropoff")
    if hidden_warehouse and role != "collection":
        if not differ: return None
        row.update(decision="review", note="donations-only pin; the page does not say people collect food here, so it was left unchanged")
        return row
    if not differ:
        return None
    note = "one collection timetable on the source page" if role == "collection" else "one timetable on the source page"
    row.update(decision="apply", note=note)
    return row

def _near(text, name):
    if not text or not name: return ""
    i = text.lower().find(name.lower()[:18])
    if i < 0: return ""
    return text[i:i + 500]

def protected(item, overrides):
    for src in (item.get("opening_times") or {}, overrides.get(item["id"]) or {}):
        if not isinstance(src, dict): continue
        if src.get("protected"): return True
        if str(src.get("reader") or "").startswith("hand-reviewed"): return True
    return False

def fetch_live(url, opener=None):
    """Open the source page now. opener is the HTTP call; there is no cache to fall back on.
    A disk file of a previous copy, including /tmp/hours_audit_cache, is never opened."""
    h = discover.host(url)
    os.makedirs(LOCK_DIR, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in ".-" else "_" for ch in (h or "none"))
    fh = open(os.path.join(LOCK_DIR, safe), "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        raw = fh.read().strip()
        try: last = float(raw) if raw else 0.0
        except ValueError: last = 0.0
        wait = GAP - (time.time() - last)
        if wait > 0: time.sleep(wait)
        rec = {"url": url, "http": None, "text": "", "error": ""}
        call = opener or _open
        for attempt in range(3):
            try:
                status, final, html = call(url)
                rec = {"url": url, "http": status, "final_url": final, "text": discover.text_of(html or ""), "error": ""}
                if status == 200 and rec["text"]: break
                rec["error"] = "HTTP %s" % status
                if status in (404, 410, 403): break
            except Exception as e:
                code = getattr(e, "code", None)
                rec = {"url": url, "http": code, "text": "", "error": str(e)[:160]}
                if code in (404, 410, 403): break
            time.sleep(2 * (attempt + 1))
        fh.seek(0); fh.truncate(); fh.write(str(time.time())); fh.flush()
        return rec
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()

def _open(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    r = urllib.request.urlopen(req, timeout=25, context=discover.CTX)
    return r.status, r.geturl(), r.read(4_000_000).decode("utf-8", "ignore")

def unclear_row(item, error):
    """Live page did not open. Nothing is read from a saved copy, and no hours are guessed."""
    shown = visible_table(item)
    ot = item.get("opening_times") or {}
    return {"id": item.get("id"), "name": item.get("name") or "", "postcode": item.get("postcode") or "",
            "source_url": ot.get("source_url") or "", "shown_days": "|".join(day_list(shown)), "source_days": "",
            "missing_days": "", "extra_days": "", "shown_hours": hours_text(shown), "source_hours": "",
            "evidence": "", "decision": "review", "note": "unclear: live source page could not be opened (%s). Opening times not listed. Call before you go." % (error or "no response"),
            "structured": {}, "raw": "", "role": ""}

def row_for(item, rec, protected_flag):
    """A row is apply only when the page opened is the listing's source URL and every recorded day and
    time is on that page. The evidence cell is a quote copied from the page. Otherwise the row is unclear
    and carries no source hours."""
    if not rec or rec.get("http") != 200 or not rec.get("text"):
        return unclear_row(item, (rec or {}).get("error") or (rec or {}).get("http"))
    wanted = (item.get("opening_times") or {}).get("source_url") or ""
    landed = rec.get("final_url") or rec.get("url") or ""
    text = rec.get("text") or ""
    if wanted and not discover.source_page_ok(wanted, landed):
        row = unclear_row(item, "redirected to %s" % landed)
        row["note"] = "unclear: source url redirected to a different page (%s). Opening times not listed. Call before you go." % landed
        return row
    row = judge_card(item, text, protected_flag)
    if row is None:
        table = discover.shown_table(item.get("opening_times"))
        if table:
            ok, quote = discover.live_hours_ok(table, text, item.get("postcode"))
            if not ok or not quote or quote not in text:
                bad = unclear_row(item, "recorded days or times could not be confirmed")
                bad["note"] = "unclear: recorded days or times could not be confirmed on the rendered page. Opening times not listed. Call before you go."
                return bad
        return None
    if row.get("decision") == "apply":
        ok, quote = discover.live_hours_ok(row.get("structured") or {}, text, item.get("postcode"))
        if not ok or not quote or quote not in text:
            row["decision"] = "review"
            row["structured"] = {}
            row["source_hours"] = ""
            row["source_days"] = ""
            row["missing_days"] = ""
            row["extra_days"] = ""
            row["raw"] = ""
            row["evidence"] = ""
            row["note"] = "unclear: recorded days or times could not be confirmed on the rendered page. Opening times not listed. Call before you go."
            return row
        row["evidence"] = quote
    return row

def stamp_copy_guard(rows):
    """The same evidence text applied to more than one postcode is not unambiguous."""
    groups = {}
    for r in rows:
        if r["decision"] != "apply": continue
        groups.setdefault((r["source_url"], r["raw"]), []).append(r)
    for grp in groups.values():
        if len(grp) < 2: continue
        pcs = {discover.norm_pc(r["postcode"]) for r in grp}
        if len(pcs) < len(grp) or len(pcs) > 1:
            for r in grp:
                r["decision"] = "review"
                r["note"] = "the same source wording covers more than one card; left unchanged"

def listings():
    data = load_full()
    items = [i for i in data["items"] if isinstance((i.get("opening_times") or {}).get("source_url"), str)
             and str(i["opening_times"]["source_url"]).startswith("http") and "helpmap.uk" not in i["opening_times"]["source_url"]]
    items.sort(key=lambda i: i["id"])
    return data, items

def shard_of(items, index, n):
    size = (len(items) + n - 1) // n
    return items[index * size:(index + 1) * size]

def shard_path(index):
    return os.path.join(ROOT, "reports", "hours_shard_%d.json" % index)

def run_shard(index, n, opener=None):
    """One of n equal shards. Each listing's source URL is opened live, once, in this process."""
    _, items = listings()
    part = shard_of(items, index, n)
    overrides = json.load(open(os.path.join(ROOT, "overrides", "opening_times.json"), encoding="utf-8"))
    rows, seen_url = [], {}
    print("shard %d/%d listings %d" % (index, n, len(part)), flush=True)
    for k, item in enumerate(part, 1):
        url = item["opening_times"]["source_url"]
        # Same URL already opened live earlier in THIS shard: reuse that response object only.
        # A file or the discover fetch cache is never read. A failed open stays failed.
        if url not in seen_url:
            seen_url[url] = fetch_live(url, opener=opener)
        rec = seen_url[url]
        row = row_for(item, rec, protected(item, overrides))
        if row: rows.append(row)
        if k % 25 == 0 or k == len(part):
            print("shard %d %d/%d" % (index, k, len(part)), flush=True)
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    json.dump({"shard": index, "shards": n, "checked": len(part), "rows": rows}, open(shard_path(index), "w", encoding="utf-8"), ensure_ascii=False)
    print("shard %d done checked %d rows %d" % (index, len(part), len(rows)), flush=True)
    return rows

def merge_shards(n, apply=False):
    parts = [json.load(open(shard_path(i), encoding="utf-8")) for i in range(n)]
    rows = [r for p in parts for r in p["rows"]]
    stamp_copy_guard(rows)
    rows.sort(key=lambda r: (r["decision"], r["id"]))
    checked = sum(p["checked"] for p in parts)
    rep = os.path.join(ROOT, "reports")
    with open(os.path.join(rep, "hours_diff.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    json.dump({"checked": checked, "shards": [{"shard": p["shard"], "checked": p["checked"], "rows": len(p["rows"])} for p in parts], "rows": rows},
              open(os.path.join(rep, "hours_live.json"), "w", encoding="utf-8"), ensure_ascii=False)
    write_review(rows, checked, apply)
    applied = [r for r in rows if r["decision"] == "apply"]
    review = [r for r in rows if r["decision"] == "review"]
    mismatched = [r for r in rows if r["source_hours"] or r["source_days"]]
    unclear = [r for r in review if r["note"].startswith("unclear:")]
    print("checked %d mismatched %d auto-fixed %d unclear %d review %d" % (checked, len(mismatched), len(applied) if apply else 0, len(unclear), len(review)), flush=True)
    return rows

def write_review(rows, checked, applied_now):
    review = [r for r in rows if r["decision"] == "review"]
    applied = [r for r in rows if r["decision"] == "apply"]
    unclear = [r for r in review if str(r.get("note") or "").startswith("unclear:")]
    lines = ["# Opening times that do not match the live source page", "",
             "Checked %d food-bank cards with a source URL on 26 Oct 2026, in 4 shards, each page opened live." % checked,
             "Mismatched (a live timetable was read and the open days or hours differ): %d. Auto-fixed: %d. Unclear (live page did not open): %d. Other review: %d."
             % (sum(1 for r in rows if r.get("source_hours") or r.get("source_days")), len(applied) if applied_now else 0, len(unclear), len(review) - len(unclear)),
             "",
             "A saved, cached, or archived copy is never used. Where the live page did not open the card is listed here and its hours are left as they were. "
             "The line for those is: Opening times not listed. Call before you go.",
             "",
             "## Needs a look", ""]
    if not review:
        lines.append("None.")
    for r in review:
        lines.append("- **%s** (%s, %s) — %s" % (r["name"], r["id"], r["postcode"], r["note"]))
        lines.append("  - source: %s" % r["source_url"])
        if r.get("shown_hours") or r.get("source_hours"):
            lines.append("  - shown: %s" % (r["shown_hours"] or "(no open-day table)"))
            lines.append("  - source: %s" % (r["source_hours"] or "(no single timetable)"))
        if r.get("evidence"):
            lines.append("  - evidence: %s" % r["evidence"][:300])
    open(os.path.join(ROOT, "reports", "hours_review.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

if __name__ == "__main__":
    args = sys.argv[1:]
    n = 4
    if "--shards" in args:
        n = int(args[args.index("--shards") + 1])
    if "--apply" in args:
        raise SystemExit("--apply was removed: this audit writes no hours. Clear mismatches reach the map only through "
                         "the strict gate (discover.times_gate_apply / times_finder.decide).")
    if "--merge" in args:
        merge_shards(n)
    elif "--shard" in args:
        run_shard(int(args[args.index("--shard") + 1]), n)
    else:
        raise SystemExit("use --shard N --shards 4, then --merge")
