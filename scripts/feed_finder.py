"""Draft proposals for new official council warm-space feeds (plan 1.3).

Reporting only. Never publishes, never edits overrides/arcgis_warmspaces.json.
Each proposal needs a hand spot-check (rule 59) and explicit 2026-27 season dates
(Grok Bot 2, 9 Nov 2026) before anyone adds the feed by PR.

Looks at the top-20 cities that do not already have a feed in
overrides/arcgis_warmspaces.json. For each, tries a small set of well-known
public URL shapes on the council's own host (warm-spaces pages and ArcGIS
FeatureServer query endpoints). A hit becomes a draft proposal with URL,
row count, season-date evidence and needs_spot_check=true.
"""
from __future__ import annotations

import json, os, re, sys, datetime
from urllib.parse import urljoin, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

OUT_JSON = "reports/official_source_proposals.json"
OUT_MD = "reports/official_source_proposals.md"
FEEDS = os.path.join(ROOT, "overrides", "arcgis_warmspaces.json")

# City -> likely council hosts (own sites only; no directories).
CITY_HOSTS = {
    "London": ["www.london.gov.uk"],  # GLA; boroughs are separate proposals later
    "Birmingham": ["www.birmingham.gov.uk"],
    "Manchester": ["www.manchester.gov.uk"],
    "Glasgow": ["www.glasgow.gov.uk"],
    "Leeds": ["www.leeds.gov.uk"],
    "Liverpool": ["www.liverpool.gov.uk"],
    "Newcastle upon Tyne": ["www.newcastle.gov.uk"],
    "Sheffield": ["www.sheffield.gov.uk"],
    "Bristol": ["www.bristol.gov.uk"],
    "Belfast": ["www.belfastcity.gov.uk"],
    "Leicester": ["www.leicester.gov.uk"],
    "Edinburgh": ["www.edinburgh.gov.uk"],
    "Cardiff": ["www.cardiff.gov.uk"],
    "Coventry": ["www.coventry.gov.uk"],
    "Bradford": ["www.bradford.gov.uk"],
    "Nottingham": ["www.nottinghamcity.gov.uk"],
    "Kingston upon Hull": ["www.hull.gov.uk"],
    "Stoke-on-Trent": ["www.stoke.gov.uk"],
    "Southampton": ["www.southampton.gov.uk"],
    "Brighton and Hove": ["www.brighton-hove.gov.uk"],  # already has a feed; skipped when registered
}

PAGE_PATHS = [
    "/warm-spaces",
    "/warmspaces",
    "/warm-spaces/",
    "/cost-of-living/warm-spaces",
    "/cost-living-support/directories/warm-welcome-directory-indoor-activities-and-places-go",
    "/health-and-social-care/welfare-and-benefits/warm-spaces/",
]

# Season evidence: explicit 2026-27 only (Bot2). A lone "updated November 2026" does not count.
SEASON_RE = re.compile(
    r"(?i)("
    r"2026\s*[–\-/]\s*27|2026/27|"
    r"winter\s+(?:of\s+)?2026(?:\s*[–\-/]\s*27)?|"
    r"(?:from\s+)?(?:1(?:st)?\s+)?sept(?:ember)?\s+2026|"
    r"sept(?:ember)?\s+2026\s*(?:to|–|-|until)\s*(?:may|april|march)\s*2027|"
    r"2026\s*(?:to|–|-|until)\s*2027"
    r")"
)
ARCGIS_RE = re.compile(
    r"https?://[^\s\"'<>]+/(?:FeatureServer|MapServer)/\d+(?:/query)?[^\s\"'<>]*",
    re.I,
)


def _load_feeds(path=None):
    try:
        raw = json.load(open(path or FEEDS, encoding="utf-8"))
    except Exception:
        return []
    return [f for f in (raw.get("feeds") or []) if f.get("url")]


def covered_hosts(feeds=None):
    hosts = set()
    for f in feeds if feeds is not None else _load_feeds():
        for key in ("url", "website"):
            u = f.get(key) or ""
            try:
                hosts.add(urlparse(u).netloc.lower())
            except Exception:
                pass
        # Brighton feed already covers that city
        if f.get("id") == "brighton-hove":
            hosts.add("www.brighton-hove.gov.uk")
    return hosts


def season_evidence(text):
    """Return the first explicit 2026-27 season match, or ''."""
    if not text:
        return ""
    m = SEASON_RE.search(text)
    return m.group(0) if m else ""


def _get(url, fetcher):
    try:
        return fetcher(url)
    except Exception as ex:
        return {"ok": False, "error": str(ex)[:160], "url": url, "text": "", "final_url": url}


def default_fetcher(url):
    """Live fetch via common.get. Tests inject a stub."""
    import common
    try:
        raw = common.get(url, tries=1, timeout=25)
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", "replace")
        else:
            text = str(raw)
        return {"ok": True, "url": url, "final_url": url, "text": text, "error": ""}
    except Exception as ex:
        return {"ok": False, "url": url, "final_url": url, "text": "", "error": str(ex)[:160]}


def probe_city(city, hosts, fetcher, covered):
    """Return a proposal dict or a 'none' record for this city."""
    name = city["name"]
    host_list = hosts or CITY_HOSTS.get(name) or []
    if not host_list:
        return {
            "city": name,
            "status": "no_host_mapping",
            "needs_spot_check": True,
            "note": "No council host mapped yet; add by hand.",
        }
    # Skip if any mapped host already has a registered feed
    if any(h.lower() in covered for h in host_list):
        return {
            "city": name,
            "status": "already_have_feed",
            "needs_spot_check": False,
            "hosts": host_list,
        }

    page_hits = []
    feed_hits = []
    for host in host_list:
        for path in PAGE_PATHS:
            url = "https://%s%s" % (host, path)
            res = _get(url, fetcher)
            if not res.get("ok"):
                continue
            text = res.get("text") or ""
            if len(text) < 80:
                continue
            if not re.search(r"(?i)warm\s*space|warm\s*welcome|warm\s*hub", text):
                continue
            season = season_evidence(text)
            page_hits.append({
                "url": res.get("final_url") or url,
                "season_evidence": season,
                "bytes": len(text),
            })
            for m in ARCGIS_RE.findall(text):
                feed_hits.append({"url": m.rstrip(").,;'\""), "from_page": url})

    if not page_hits and not feed_hits:
        return {
            "city": name,
            "status": "council_publishes_none_found",
            "needs_spot_check": True,
            "hosts": host_list,
            "note": "No warm-space page or ArcGIS link found on the mapped host paths this run.",
        }

    # Prefer a feed URL with season evidence on the referring page
    best_page = next((p for p in page_hits if p.get("season_evidence")), page_hits[0] if page_hits else None)
    proposal = {
        "city": name,
        "status": "proposal",
        "needs_spot_check": True,  # rule 59
        "hosts": host_list,
        "page_url": (best_page or {}).get("url") or "",
        "feed_url": (feed_hits[0]["url"] if feed_hits else ""),
        "season_evidence": (best_page or {}).get("season_evidence") or "",
        "season_ok": bool((best_page or {}).get("season_evidence")),
        "row_count": None,  # filled only after a hand check of the feed
        "licence_or_sharing": "unknown — check the council page before adding",
        "note": (
            "Draft only. Add to overrides/arcgis_warmspaces.json by PR after a hand spot-check "
            "and only when season_ok is true (explicit 2026-27 dates)."
        ),
    }
    if not proposal["season_ok"]:
        proposal["note"] += " Held: no explicit 2026-27 season dates on the page (Bot2)."
    return proposal


def run(cities=None, fetcher=None, feeds=None, root=None, write=True):
    """Build proposals for top-20 cities. Returns the report dict."""
    root = root or ROOT
    import city_watch
    cities = cities or city_watch.CITIES
    fetcher = fetcher or default_fetcher
    covered = covered_hosts(feeds)
    day = datetime.date.today().isoformat()
    proposals = [probe_city(c, CITY_HOSTS.get(c["name"]), fetcher, covered) for c in cities]
    report = {
        "day": day,
        "rule": "plan 1.3 official feed finder — proposals only, rule 59 spot-check required",
        "proposals": proposals,
        "summary": {
            "cities": len(proposals),
            "already_have_feed": sum(1 for p in proposals if p["status"] == "already_have_feed"),
            "proposal": sum(1 for p in proposals if p["status"] == "proposal"),
            "season_ok": sum(1 for p in proposals if p.get("season_ok")),
            "none_found": sum(1 for p in proposals if p["status"] == "council_publishes_none_found"),
        },
    }
    if write:
        os.makedirs(os.path.join(root, "reports"), exist_ok=True)
        jp = os.path.join(root, OUT_JSON)
        mp = os.path.join(root, OUT_MD)
        with open(jp, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")
        lines = [
            "# Official warm-space source proposals — %s" % day,
            "",
            "Drafts only. Nothing was published. Each proposal needs a hand spot-check (rule 59)",
            "and explicit 2026-27 season dates before a feed is added by PR.",
            "",
            "Summary: %(cities)d cities — %(already_have_feed)d already have a feed, "
            "%(proposal)d proposals, %(season_ok)d with season dates, %(none_found)d none found."
            % report["summary"],
            "",
        ]
        for p in proposals:
            lines.append("## %s — %s" % (p["city"], p["status"]))
            if p.get("page_url"):
                lines.append("- page: %s" % p["page_url"])
            if p.get("feed_url"):
                lines.append("- feed: %s" % p["feed_url"])
            if p.get("season_evidence"):
                lines.append("- season evidence: %s" % p["season_evidence"])
            if p.get("note"):
                lines.append("- note: %s" % p["note"])
            lines.append("- needs spot-check: %s" % p.get("needs_spot_check"))
            lines.append("")
        open(mp, "w", encoding="utf-8").write("\n".join(lines))
    return report


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    dry = "--dry" in argv
    report = run(write=not dry)
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
