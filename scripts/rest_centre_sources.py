"""Council news and emergencies pages for rest centre (council-run) checks.

Discover links from each council website already listed in scripts/sweep_sources.json.
A URL is kept only after it returns HTTP 200 on that council's own site. Councils
with no verified news page are listed in reports/rest_centre_sources.md. Nothing is guessed.
"""
import html as html_lib, json, os, re, ssl, threading, time, urllib.error, urllib.parse, urllib.request
import concurrent.futures as cf

SRC = "overrides/rest_centre_sources.json"
REPORT = "reports/rest_centre_sources.md"
LOG = "logs/rest_centre_status.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.8"}
NEWS_PATH = re.compile(r"/(newsroom|latest-news|news-and-events|news|press-releases|press|media-centre|media-center|newyddion)(/|$|-)", re.I)
NEWS_TEXT = re.compile(r"\b(newsroom|latest news|news|press releases|newyddion|naidheachdan)\b", re.I)
EMERG_PATH = re.compile(r"/(emergencies|emergency-planning|emergency-information|major-incident|major-incidents|flooding|flood-alerts|flooding-advice|civil-contingencies|prepare-for-emergencies)(/|$|-)", re.I)
EMERG_TEXT = re.compile(r"\b(major incidents?|emergencies|emergency planning|flooding|flood alerts|civil contingencies)\b", re.I)
SKIP = re.compile(r"\.(pdf|docx?|jpe?g|png|zip)(\?|$)|mailto:|tel:|facebook\.com|twitter\.com|x\.com|instagram\.com|youtube\.com|linkedin\.com", re.I)
BAD_PATH = re.compile(r"planning-application|building-control|comment-on-a-planning", re.I)
HREF = re.compile(r'href\s*=\s*["\']([^"\'#]+)["\']', re.I)
ANCHOR = re.compile(r'<a\b[^>]*href\s*=\s*["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.I | re.S)
_TLS = ssl.create_default_context()
_NO_TLS = ssl._create_unverified_context()


def registrable(host):
    h = (host or "").lower().split(":")[0]
    if h.startswith("www."):
        h = h[4:]
    parts = [p for p in h.split(".") if p]
    if len(parts) >= 3 and ".".join(parts[-2:]) in ("gov.uk", "gov.scot", "gov.wales", "org.uk"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else h


def same_site(base, url):
    try:
        b, u = urllib.parse.urlparse(base), urllib.parse.urlparse(url)
    except Exception:
        return False
    if u.scheme not in ("http", "https"):
        return False
    return bool(registrable(b.netloc)) and registrable(b.netloc) == registrable(u.netloc)


def _depth(url):
    path = urllib.parse.urlparse(url).path.strip("/")
    return path.count("/") + (1 if path else 0)


def score_link(url, text, kind):
    if not url or SKIP.search(url) or BAD_PATH.search(urllib.parse.urlparse(url).path):
        return 0
    path = urllib.parse.urlparse(url).path
    host = urllib.parse.urlparse(url).netloc.lower()
    path_rx, text_rx = (NEWS_PATH, NEWS_TEXT) if kind == "news" else (EMERG_PATH, EMERG_TEXT)
    path_hit = bool(path_rx.search(path)) or (kind == "news" and (host.startswith("news.") or ".news." in host))
    text_hit = bool(text_rx.search(text or ""))
    if not path_hit and not text_hit:
        return 0
    depth = _depth(url)
    slug = path.strip("/").split("/")[-1] if path.strip("/") else ""
    if re.search(r"/20\d\d/", path) or depth >= 4:
        return 1 if path_hit else 0
    score = 0
    if host.startswith("news.") or host.startswith("newsroom."):
        score += 8
    if path_hit and depth <= 2:
        score += 8
    if re.search(r"/(newsroom|news|news-archive|press|emergencies|emergency-planning|flooding)/?$", path, re.I):
        score += 4
    if text_hit:
        score += 3
    if depth >= 2 and len(slug) > 28:
        score = min(score, 4)
    return score


def links_from(html, base):
    found = {}
    raw = html_lib.unescape(html or "")
    for href, inner in ANCHOR.findall(raw):
        text = re.sub(r"<[^>]+>", " ", inner)
        text = re.sub(r"\s+", " ", text).strip()
        full = urllib.parse.urljoin(base, html_lib.unescape(href)).split("#")[0]
        found[full] = text
    for href in HREF.findall(raw):
        full = urllib.parse.urljoin(base, html_lib.unescape(href)).split("#")[0]
        found.setdefault(full, "")
    return [(u, t) for u, t in found.items() if same_site(base, u)]


def choose_pages(base, links):
    """Pick the best news page and, where a link exists, the emergencies page. No network."""
    best = {"news": (0, None), "emergencies": (0, None)}
    for url, text in links or []:
        if not same_site(base, url):
            continue
        for kind in ("news", "emergencies"):
            s = score_link(url, text, kind)
            if s >= 3 and (s > best[kind][0] or (s == best[kind][0] and best[kind][1] and _depth(url) < _depth(best[kind][1]))):
                best[kind] = (s, url)
    return {"news": best["news"][1], "emergencies": best["emergencies"][1]}


class HostGate:
    def __init__(self, gap=0.35):
        self.gap = gap
        self._lock = threading.Lock()
        self._next = {}
        self._hosts = {}

    def wait(self, host):
        with self._lock:
            lk = self._hosts.setdefault(host, threading.Lock())
        with lk:
            now = time.monotonic()
            nxt = self._next.get(host, 0)
            if now < nxt:
                time.sleep(nxt - now)
            self._next[host] = time.monotonic() + self.gap


_GATE = HostGate()


def fetch(url, timeout=12, gate=None):
    gate = gate or _GATE
    host = urllib.parse.urlparse(url).netloc.lower()
    gate.wait(host)
    req = urllib.request.Request(url, headers=UA)
    last = {"http": None, "url": url, "html": "", "error": ""}
    for ctx in (_TLS, _NO_TLS):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                raw = r.read(1_200_000)
                return {"http": r.status, "url": r.geturl(), "html": raw.decode("utf-8", "ignore"), "error": ""}
        except urllib.error.HTTPError as e:
            return {"http": e.code, "url": url, "html": "", "error": ""}
        except Exception as e:
            last = {"http": None, "url": url, "html": "", "error": type(e).__name__}
            if "CERTIFICATE" not in type(e).__name__.upper() and "SSL" not in str(e).upper():
                break
    return last


def load(path=None):
    path = path or SRC
    if not os.path.exists(path):
        return {"councils": [], "unresolved": []}
    return json.load(open(path, encoding="utf-8"))


def urls_for_council(council, sources=None, swep_sources=None):
    """News, emergencies and severe weather shelter (SWEP) page URLs for one council."""
    code, name = council.get("code"), council.get("name") or council.get("council")
    out = []
    for c in (sources or load()).get("councils") or []:
        if c.get("code") == code or c.get("council") == name:
            for key in ("news", "emergencies"):
                if c.get(key):
                    out.append(c[key])
    if swep_sources is None and os.path.exists("overrides/swep_sources.json"):
        try:
            swep_sources = json.load(open("overrides/swep_sources.json", encoding="utf-8"))
        except Exception:
            swep_sources = []
    swep_sources = swep_sources or []
    for x in swep_sources or []:
        if x.get("url") and (x.get("code") == code or x.get("council") == name):
            out.append(x["url"])
    return list(dict.fromkeys(out))


LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


def sitemap_links(base, fetcher, limit=600):
    """Links from the council's own sitemap, used only when the homepage has no news link."""
    robots = fetcher(urllib.parse.urljoin(base, "/robots.txt"))
    maps = re.findall(r"(?i)Sitemap:\s*(\S+)", robots.get("html") or "")
    if not maps:
        maps = [urllib.parse.urljoin(base, "/sitemap.xml")]
    out, seen, queue = [], set(), maps[:2]
    while queue and len(out) < limit:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        page = fetcher(u)
        if page.get("http") != 200:
            continue
        body = page.get("html") or ""
        locs = []
        for loc in LOC.findall(body)[:limit]:
            loc = html_lib.unescape(loc).strip()
            if not loc.lower().startswith("http"):
                loc = urllib.parse.urljoin(base, loc)
            if loc.lower().startswith("http"):
                locs.append(loc.split("#")[0])
        if "<sitemapindex" in body.lower() and len(queue) < 4:
            queue.extend(loc for loc in locs[:3] if loc not in seen)
            continue
        for loc in locs:
            if same_site(base, loc):
                out.append((loc, ""))
    return out


def discover(councils=None, fetcher=None, out_path=SRC, report_path=REPORT, threads=8, timeout=12):
    fetcher = fetcher or (lambda u: fetch(u, timeout=timeout))
    if councils is None:
        councils = json.load(open("scripts/sweep_sources.json", encoding="utf-8"))["councils"]
    def one(c):
        site = c.get("site") or ""
        home = fetcher(site) if site else {"http": None, "html": "", "url": site}
        final = home.get("url") or site
        if home.get("http") != 200:
            why = "council website returned HTTP %s" % (home.get("http") or home.get("error") or "no response")
            return {"code": c["code"], "council": c["name"], "nation": c.get("nation"), "site": site,
                    "news": None, "emergencies": None, "unresolved": why}
        links = links_from(home.get("html") or "", final)
        chosen = choose_pages(final, links)
        if not chosen.get("news"):
            chosen = choose_pages(final, links + sitemap_links(final, fetcher))
        verified = {}
        for kind, url in chosen.items():
            if not url:
                verified[kind] = None
                continue
            page = fetcher(url)
            ok = page.get("http") == 200 and same_site(final, page.get("url") or url)
            verified[kind] = (page.get("url") or url) if ok else None
        reason = None if verified.get("news") else "no news or newsroom page found on the council website"
        return {"code": c["code"], "council": c["name"], "nation": c.get("nation"), "site": final,
                "news": verified.get("news"), "emergencies": verified.get("emergencies"), "unresolved": reason}
    def safe(c):
        try:
            return one(c)
        except Exception as e:
            return {"code": c.get("code"), "council": c.get("name"), "nation": c.get("nation"), "site": c.get("site"),
                    "news": None, "emergencies": None, "unresolved": "council website could not be read (%s)" % type(e).__name__}
    with cf.ThreadPoolExecutor(threads) as ex:
        rows = list(ex.map(safe, councils))
    unresolved = [{"code": r["code"], "council": r["council"], "reason": r["unresolved"]} for r in rows if r.get("unresolved")]
    payload = {"checked": time.strftime("%Y-%m-%d"), "councils": [{k: r[k] for k in ("code", "council", "nation", "site", "news", "emergencies")} for r in rows],
               "unresolved": unresolved}
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    json.dump(payload, open(out_path, "w"), indent=1, ensure_ascii=False)
    os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
    covered = [r for r in rows if r.get("news")]
    lines = ["# Rest centre (council-run) sources", "",
             "%d councils. %d with a verified news or newsroom page. %d unresolved (no news page verified; nothing guessed)." % (len(rows), len(covered), len(unresolved)),
             "%d also have an emergencies, major incident or flooding page." % sum(1 for r in rows if r.get("emergencies")), "",
             "## Unresolved", ""]
    lines += ["- %s (%s): %s" % (r["council"], r["code"], r["unresolved"]) for r in rows if r.get("unresolved")] or ["None."]
    lines += ["", "## No emergencies, major incident or flooding page found", ""]
    lines += ["- %s (%s)" % (r["council"], r["code"]) for r in rows if r.get("news") and not r.get("emergencies")] or ["None."]
    open(report_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return payload


def fetch_pages(rows=None, fetcher=None, run_day=None, threads=6, timeout=10, budget_s=480):
    """Fetch listed pages and run the visible-text rest centre scanner. Returns (pages, seconds)."""
    if rows is None:
        rows = []
        for c in load().get("councils") or []:
            for kind in ("news", "emergencies"):
                if c.get(kind):
                    rows.append({"council": c["council"], "code": c.get("code"), "url": c[kind], "kind": kind})
    if not rows:
        return [], 0.0
    fetcher = fetcher or (lambda u: fetch(u, timeout=timeout))
    t0 = time.monotonic()
    def one(row):
        if time.monotonic() - t0 > budget_s:
            return None
        r = fetcher(row["url"])
        page = {"council": row.get("council") or "", "url": row["url"], "kind": row.get("kind") or "",
                "http": r.get("http"), "status": "checked" if r.get("http") == 200 else "unreachable",
                "quote": "", "rest_centre": None}
        if r.get("http") == 200:
            from page_visible import html_to_visible_text
            import incident_rest_centre_switch_on as irso
            txt = html_to_visible_text(r.get("html") or r.get("text") or "")
            irso.enrich_page(page, txt, run_day)
        return page
    with cf.ThreadPoolExecutor(threads) as ex:
        pages = [p for p in ex.map(one, rows) if p]
    return pages, time.monotonic() - t0


def save_log(pages, run_day, seconds, path=LOG):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    clean = []
    for p in pages or []:
        q = dict(p)
        q.pop("_text", None)
        clean.append(q)
    json.dump({"run": run_day, "seconds": round(seconds or 0, 1), "pages": clean,
               "on": [p["council"] for p in clean if (p.get("rest_centre") or {}).get("active")]},
              open(path, "w"), indent=1, ensure_ascii=False)


def load_log_pages(path=LOG):
    try:
        return json.load(open(path, encoding="utf-8")).get("pages") or []
    except Exception:
        return []


if __name__ == "__main__":
    import sys
    t0 = time.monotonic()
    if sys.argv[1:] == ["discover"]:
        out = discover()
        print("councils", len(out["councils"]), "unresolved", len(out["unresolved"]), "in %.0fs" % (time.monotonic() - t0))
    elif sys.argv[1:] == ["scan"]:
        pages, seconds = fetch_pages()
        save_log(pages, time.strftime("%Y-%m-%d"), seconds)
        print("rest centre (council-run) scan: %d pages in %.0fs" % (len(pages), seconds))
    else:
        print("usage: rest_centre_sources.py discover|scan")
