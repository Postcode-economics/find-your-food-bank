"""Incident rest centre watch, every 10 minutes.

Reads the official warning feeds in scripts/weather.py. A Met Office amber or red warning,
or a severe flood warning (those feeds mark it level red), re-scans only that council's
rest centre pages: its severe weather shelter (SWEP) pages plus its news and emergencies pages.
The warning itself never becomes a card. ON and OFF go through scripts/incident_rest_centre_switch_on,
the same state, waiting list, issue and live file as the shelters refresh. A page that is
already on does not open a second issue. Cards whose council page no longer says the rest
centre is open come down on this run. A card also comes down 24 hours after it was added
unless a later check of the council page still says it is open.
"""
import datetime, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weather

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WATCH_LEVELS = ("amber", "red")  # severe flood warnings are level red on these feeds


def feed_get(url, headers=None):
    return weather.get(url, headers, timeout=8)


def triggering_warnings(warnings):
    return [w for w in warnings or [] if w.get("level") in WATCH_LEVELS]


def councils_to_scan(warnings, councils):
    hit = {}
    for w in triggering_warnings(warnings):
        for c in weather.councils_hit(w, councils):
            hit[c.get("code") or c.get("name")] = c
    return list(hit.values())


def live_source_urls(root):
    import incident_rest_centre_live as live
    urls = []
    state = live.load_state(os.path.join(root, live.STATE))
    for v in (state.get("incidents") or {}).values():
        card = v.get("card") or {}
        u = card.get("source_url") or v.get("url")
        if u:
            urls.append(u)
    return urls


def _rows_for(urls, councils, sources, swep_sources):
    by_url = {}
    for c in councils:
        for u in __import__("rest_centre_sources").urls_for_council(c, {"councils": sources}, swep_sources):
            by_url.setdefault(u, c.get("name") or c.get("council") or "")
    rows = []
    for u in urls:
        rows.append({"council": by_url.get(u, ""), "url": u, "kind": "watch"})
    return rows


def run(root=None, warnings=None, getter=None, fetcher=None, now=None, councils=None, sources=None, swep_sources=None):
    """Return a result dict. Council pages are fetched only for a triggering warning or a live card."""
    root = root or os.getcwd()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    t0 = time.monotonic()
    errs = []
    if warnings is None:
        warnings, errs, _notes = weather.fetch_all(getter or feed_get, weather.nrw_key())
        primary = [e for e in errs if not str(e).startswith("Natural Resources Wales")]
        if len(primary) >= 4 and not warnings:
            raise RuntimeError("warning feeds failed: " + "; ".join(primary))
    if councils is None:
        councils = json_load(os.path.join(root, "scripts", "sweep_sources.json")).get("councils") or []
    if sources is None:
        import rest_centre_sources as rcs
        sources = (rcs.load(os.path.join(root, rcs.SRC)).get("councils") or [])
    if swep_sources is None:
        swep_sources = json_load(os.path.join(root, "overrides", "swep_sources.json"), default=[])
    hit = councils_to_scan(warnings, councils)
    urls = []
    import rest_centre_sources as rcs
    for c in hit:
        urls.extend(rcs.urls_for_council(c, {"councils": sources}, swep_sources))
    for u in live_source_urls(root):
        if u not in urls:
            urls.append(u)
    urls = list(dict.fromkeys(urls))
    pages = []
    seconds = 0.0
    if urls:
        rows = [{"council": "", "url": u, "kind": "watch"} for u in urls]
        # name the council when we know it
        named = {u: row for row in _rows_for(urls, councils, sources, swep_sources) for u in [row["url"]]}
        rows = [named.get(u) or {"council": "", "url": u, "kind": "watch"} for u in urls]
        pages, seconds = rcs.fetch_pages(rows=rows, fetcher=fetcher, run_day=now.date().isoformat(), threads=4, timeout=8, budget_s=90)
    import incident_rest_centre_switch_on as irso
    prev = irso.load_snapshot(root)
    changed = False
    opened = closed = 0
    if pages:
        by = {p.get("url"): p for p in prev}
        for p in pages:
            if p.get("http") != 200 and p.get("url") in by:
                continue  # unreachable: keep the last reading; the 24h limit still applies
            by[p.get("url")] = p
        merged = list(by.values())
        result = irso.apply(prev, merged, run_day=now.date().isoformat(), root=root, detected_at=now, allow_first=not prev)
        if result.get("error"):
            raise RuntimeError(result["error"])
        opened, closed = result.get("opened") or 0, result.get("closed") or 0
        changed = bool(opened or closed or result.get("live_changed"))
    import incident_rest_centre_live as live
    expired = live.drop_expired(root, now)
    if expired:
        changed = True
        for v in expired:
            card = v.get("card") or {}
            irso.close_activation(card.get("opened_by") or v.get("council") or "", card.get("name") or "Rest centre",
                                  comment="Rest centre alert removed: 24 hours since it was added, and the council page has not confirmed it is still open.",
                                  category=irso.INCIDENT_LABEL)
            closed += 1
    return {"warnings": len(warnings or []), "triggering": len(triggering_warnings(warnings)),
            "councils": [c.get("code") for c in hit], "fetched": len(pages), "opened": opened, "closed": closed,
            "expired": len(expired), "changed": changed, "seconds": round(time.monotonic() - t0, 1), "errors": errs}


def json_load(path, default=None):
    try:
        return __import__("json").load(open(path, encoding="utf-8"))
    except Exception:
        return [] if default is None else default


def main(argv=None):
    os.chdir(ROOT)
    try:
        result = run(root=ROOT)
    except Exception as e:
        print("::error::Incident rest centre watch failed: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 1
    print("incident rest centre watch: %d triggering warnings, %d councils, %d pages, %.0fs%s" % (
        result["triggering"], len(result["councils"]), result["fetched"], result["seconds"],
        "" if result["triggering"] or result["fetched"] else " (no warning, no council pages fetched)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
