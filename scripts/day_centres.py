"""Candidate sources for day centres. They are not shelters.

Council pages whose URL is a day centre or rough-sleeping page, and Homeless Link's
day-centre category (service_types=day-centre), are recorded as candidates. They stay
held until a separate Day centre label exists, and even then this module does not publish
them: a reviewed PR applies the label. Nothing here writes a phone or a council line.
"""
import json, os, re, datetime, urllib.parse
import discover
import follow_through
import city_watch

ROOT = follow_through.ROOT
LOG = "logs/day_centre_candidates.json"
HL_SEARCH = "https://homeless.org.uk/homeless-england/"
DAY_URL = re.compile(r"day-?centres?(?:/|$|\.|\?)|rough-?sleep", re.I)
DAY_WORD = re.compile(r"day\s*centres?", re.I)
TAG = "day centre candidates"


def label_ready():
    """True only when separate work has defined the Day centre label. This file does not create it."""
    try:
        import day_centre_label
    except ImportError:
        return False
    return getattr(day_centre_label, "LABEL", None) == "Day centre"


def filter_urls(urls):
    return [u for u in urls or [] if DAY_URL.search(u or "")]


def sitemap_locs(xml):
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml or "")


def _name_before(text, at):
    chunk = (text or "")[max(0, at - 180):at]
    chunk = re.split(r"[.\n|]", chunk)[-1]
    parts = [p.strip(" -–,:") for p in re.split(r"\s[-–]\s|,", chunk) if p.strip()]
    titled = list(re.finditer(r"([A-Z][\w'’]*(?:\s+[A-Z][\w'’]*){0,5}\s+day centres?)", chunk))
    if titled:
        return re.sub(r"\s+", " ", titled[-1].group(1))[:80]
    named = [p for p in parts if DAY_WORD.search(p)]
    if named:
        return re.sub(r"\s+", " ", named[-1])[:80]
    for p in parts:
        if re.search(r"\d", p):
            continue
        if discover.tokens(p):
            return re.sub(r"\s+", " ", p)[:80]
    return ""


def _strip_private(row):
    for k in follow_through.PHONE_KEYS:
        row.pop(k, None)
    return row


def parse_council_page(html, url, council=""):
    """Venue blocks on a day-centre page, or day-centre blocks on a rough-sleeping page."""
    text = discover.text_of(html or "")
    url_day = bool(re.search(r"day.centre", url or "", re.I))
    url_rough = bool(re.search(r"rough.sleep", url or "", re.I))
    if not url_day and not url_rough:
        return []
    upper = text.upper()
    pcs = list(discover.PC_RE.finditer(upper))
    out = []
    for i, m in enumerate(pcs):
        pc = (m.group(1) + " " + m.group(2)).upper()
        start = pcs[i - 1].end() if i else max(0, m.start() - 180)
        end = pcs[i + 1].start() if i + 1 < len(pcs) else len(text)
        window = text[start:end]
        if url_rough and not url_day and not DAY_WORD.search(window):
            continue
        if re.search(r"night shelter|\bhostel\b", window, re.I) and not DAY_WORD.search(window):
            continue
        name = _name_before(text, m.start())
        if not name:
            continue
        quote = follow_through.quote_for_venue(window, name, pc) or ""
        row = _strip_private({
            "id": "dc-" + re.sub(r"[^a-z0-9]+", "-", (name + "-" + pc).lower())[:80].strip("-"),
            "name": name,
            "postcode": pc,
            "source_url": url,
            "website": url,
            "council": council,
            "source": "council day centre / rough sleeping page",
            "day_time_quote": quote or "",
            "status": "held",
            "publish": False,
        })
        out.append(row)
    return out


def parse_homeless_link_search(html):
    return sorted(set(re.findall(r"service/([a-z0-9-]+)", html or "")))


def candidate_from_service(slug, html, url):
    import directories
    parsed = directories.parse_hl_service(slug, html or "")
    name = parsed.get("name") or slug.replace("-", " ").title()
    pc = parsed.get("postcode") or ""
    text = discover.text_of(html or "")
    quote = follow_through.quote_for_venue(text, name, pc) if pc or name else ""
    return _strip_private({
        "id": "dc-hl-" + slug[:70],
        "name": name,
        "postcode": pc,
        "address": parsed.get("address") or "",
        "source_url": url,
        "website": parsed.get("website") or url,
        "source": "Homeless Link day centre category",
        "day_time_quote": quote or "",
        "status": "held",
        "publish": False,
    })


def council_slice(councils, day, limit):
    councils = list(councils or [])
    if not councils or limit <= 0:
        return []
    n = datetime.date.fromisoformat(day).timetuple().tm_yday - 1
    start = (n * limit) % len(councils)
    return (councils[start:] + councils[:start])[:limit]


def _as_html(res):
    if not res:
        return ""
    return res.get("html") or res.get("raw") or res.get("text") or ""


def collect_pages(pages, root, day, label_ready_fn=None, hl_services=()):
    """Hold candidates from already-fetched pages. Writes the log and the pending section only."""
    label_ready_fn = label_ready_fn or label_ready
    ready = bool(label_ready_fn())
    found = []
    for p in pages or []:
        found += parse_council_page(p.get("html") or "", p.get("url") or "", p.get("council") or "")
    for slug, html, url in hl_services or ():
        found.append(candidate_from_service(slug, html, url))
    # de-dupe by id
    by = {}
    for row in found:
        if not row.get("id"):
            continue
        row["label"] = "Day centre" if ready else ""
        row["why"] = ("held for the Day centre label; not published as a shelter" if ready
                      else "Day centre label is not on the map yet; held as a candidate")
        row["checked_on"] = day
        by[row["id"]] = _strip_private(row)
    path = os.path.join(root, LOG)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {
        "generated": day,
        "label_ready": ready,
        "note": "Day centre candidates. Not shelters. Not published. A reviewed PR can apply them only through the Day centre label, once that label exists.",
        "candidates": [by[k] for k in sorted(by)],
    }
    tmp = path + ".tmp"
    json.dump(doc, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    lines = ["## Day centre candidates (held)", "",
             "Council day-centre / rough-sleeping pages and Homeless Link's day-centre category. Not on the map.",
             "Publish only via the Day centre label once that label exists. Until then these stay held.", ""]
    show = doc["candidates"][:25]
    if not show:
        lines.append("- none this run")
    for c in show:
        bits = "- %s (%s)" % (c.get("name") or "?", c.get("postcode") or "")
        if c.get("day_time_quote"):
            bits += " — " + c["day_time_quote"][:80]
        bits += " — " + (c.get("source_url") or "")
        lines.append(bits)
    extra = len(doc["candidates"]) - len(show)
    if extra > 0:
        lines.append("- and %d more in logs/day_centre_candidates.json" % extra)
    city_watch.replace_section(os.path.join(root, "reports", "pending_dean.md"), TAG, lines)
    if ready:
        hits = []
        for c in doc["candidates"]:
            if c.get("day_time_quote") and c.get("source_url"):
                hits.append({
                    "passed": True, "id": c["id"], "layer": "day_centres", "name": c["name"],
                    "postcode": c.get("postcode") or "", "evidence_url": c["source_url"],
                    "day_time_quote": c["day_time_quote"], "source_url": c["source_url"],
                    "website": c.get("website") or "", "found_via": "day centre source",
                    "checked_on": day, "rule": "official or own page states a weekday and a time",
                    "label": "Day centre",
                })
        follow_through.merge_proposal(hits, root, day)
    return doc


def _fetch_council_pages(councils, budget, page_cap):
    pages, left = [], page_cap
    for c in councils:
        if left <= 0:
            break
        base = (c.get("site") or "").rstrip("/")
        if not base.startswith("http"):
            continue
        sm = budget.fetch(base + "/sitemap.xml")
        locs = filter_urls(sitemap_locs(_as_html(sm)))
        # one child sitemap if the first document is an index with no day-centre locs
        if not locs:
            kids = [u for u in sitemap_locs(_as_html(sm)) if u.lower().endswith(".xml")][:1]
            for kid in kids:
                locs = filter_urls(sitemap_locs(_as_html(budget.fetch(kid))))
                if locs:
                    break
        for u in locs[:2]:
            if left <= 0:
                break
            res = budget.fetch(u)
            if res.get("reason") == "host budget":
                continue
            pages.append({"url": res.get("final_url") or u, "html": _as_html(res), "council": c.get("name") or ""})
            left -= 1
    return pages


def _fetch_homeless_link(budget, maxpages):
    slugs = []
    for p in range(1, maxpages + 1):
        url = HL_SEARCH + "?" + urllib.parse.urlencode({"query": "day centre", "service_types": "day-centre", "page": p})
        res = budget.fetch(url)
        found = parse_homeless_link_search(_as_html(res))
        if not found:
            break
        slugs.extend(found)
    out, seen = [], set()
    for slug in slugs:
        if slug in seen:
            continue
        seen.add(slug)
        url = "https://homeless.org.uk/homeless-england/service/%s/" % slug
        res = budget.fetch(url)
        if res.get("http") != 200:
            continue
        out.append((slug, _as_html(res), url))
        if len(out) >= 15:
            break
    return out


def collect(root=None, fetcher=None, day=None, councils=None, page_cap=None, council_cap=None, hl_pages=2, label_ready_fn=None, gap=1.0):
    """Bounded, polite collect. Default councils come from scripts/sweep_sources.json."""
    root = root or ROOT
    day = day or datetime.date.today().isoformat()
    fetcher = fetcher or discover.fetch_raw
    page_cap = int(os.environ.get("DAY_CENTRE_PAGES", "20") if page_cap is None else page_cap)
    council_cap = int(os.environ.get("DAY_CENTRE_COUNCILS", "25") if council_cap is None else council_cap)
    if councils is None:
        try:
            src = json.load(open(os.path.join(root, "scripts", "sweep_sources.json"), encoding="utf-8"))
            councils = src.get("councils") or []
        except Exception:
            councils = []
    chosen = council_slice(councils, day, council_cap)
    budget = follow_through.Budget(fetcher, per_host=6, gap=gap, render=False)
    try:
        pages = _fetch_council_pages(chosen, budget, page_cap)
    except Exception as ex:
        print("day centre council pages skipped: %s" % ex)
        pages = []
    try:
        services = _fetch_homeless_link(budget, hl_pages) if hl_pages else []
    except Exception as ex:
        print("Homeless Link day centres skipped: %s" % ex)
        services = []
    return collect_pages(pages, root, day, label_ready_fn=label_ready_fn, hl_services=services)


def main(argv=None):
    import sys
    argv = argv if argv is not None else sys.argv
    try:
        doc = collect()
        print("day centre candidates held: %d (label ready: %s)" % (len(doc.get("candidates") or []), doc.get("label_ready")))
    except Exception as ex:
        print("day centre sources failed: %s" % ex)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
