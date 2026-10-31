"""Follow a generic council or organisation page through to the venue's own page.

Dean's 21 Oct 2026 bar is unchanged: a place is published only when an official or own page
states a weekday and a time. This module does not publish. When that evidence is found, the
sweep writes reports/verified_new_places.json for a reviewed PR to apply. Anything that does
not meet the bar stays held.

Fetches are polite (a gap per host), cached, and capped per host. The same fetch and render
helpers as the rest of the refresh are used. Phone and council-line fields are never read or written.
"""
import json, os, re, time, threading, urllib.parse
import discover

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROPOSAL = "reports/verified_new_places.json"
SEEN = "logs/follow_through_seen.json"
DIRECTORY_HOSTS = {"warmwelcome.uk", "homeless.org.uk", "homelesslink.org.uk"}
SKIP_PARTS = ("facebook.com", "instagram.com", "twitter.com", "x.com/", "linktr.ee", "google.com", "bit.ly", "goo.gl")
INDEX_PATH = re.compile(
    r"/(warm-?(spaces?|hubs?|places?|welcome)|libraries|find-a-library|community-centres?|"
    r"our-(venues|centres|centers|libraries)|locations|whats-on|day-?centres?|rough-?sleep|"
    r"cost-of-living|warm-welcoming-spaces|leisure-centres?)/?$", re.I)
CLOCK = re.compile(r"\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{1,2}:\d{2}", re.I)
DAYW = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)", re.I)
ASSET = re.compile(r"\.(pdf|jpg|jpeg|png|gif|svg|zip|css|js|xml)(\?|$)", re.I)
PHONE_KEYS = {"phone", "tel", "council_phone", "council_ooh", "council_label", "council_label_cy"}
STORE = ("id", "layer", "name", "postcode", "address", "lat", "lng", "evidence_url", "day_time_quote",
         "source_url", "website", "found_via", "checked_on", "rule")
LAYER = {"ws": "warmspaces", "sh": "shelters", "dc": "day_centres"}


def normalise_website(u):
    u = (u or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    if not re.match(r"https?://", u, re.I):
        if "." in u.split("/")[0]:
            u = "https://" + u
    return u


def render_enabled():
    return os.environ.get("FOLLOW_RENDER", "") == "1"


def default_render(url):
    """Headless render (scripts/render_fetch.py). None when Playwright is not available."""
    try:
        import render_fetch
        return render_fetch.fetch(url)
    except Exception:
        return None


def root_from_log(log_path):
    if not log_path:
        return None
    d = os.path.dirname(os.path.abspath(log_path))
    if os.path.basename(d) == "logs":
        return os.path.dirname(d)
    return None


def _gov(url):
    return bool(discover.GOV.search(discover.host(url)))


def _directory(url):
    return discover.host(url) in DIRECTORY_HOSTS


def _index_path(url):
    path = urllib.parse.urlparse(url or "").path or "/"
    if path.strip("/").lower() in ("", "index.html", "index.php", "home"):
        return True
    return bool(INDEX_PATH.search(path if path.endswith("/") else path + "/")) or bool(INDEX_PATH.search(path))


def _host_blob(url):
    return re.sub(r"[^a-z0-9]", "", discover.host(url))


def host_shares_name(url, name):
    ht = discover.tokens(discover.host(url).replace(".", " "))
    nt = discover.tokens(name)
    if not nt:
        return False
    if ht & nt:
        return True
    blob = _host_blob(url)
    return any(w in blob for w in nt if len(w) > 4)


def _name_window(text, name):
    nt = sorted(discover.tokens(name), key=len, reverse=True)
    if not nt:
        return None
    low = (text or "").lower()
    i = low.find(nt[0])
    if i < 0:
        return None
    return text[max(0, i - 400):i + 500]


def quote_for_venue(text, name, postcode):
    """Weekday + clock time tied to this venue, or None. Never guesses across a multi-venue page."""
    text = text or ""
    pc = discover.norm_pc(postcode)
    if pc and pc in text.upper().replace(" ", ""):
        block = discover.postcode_block(text, postcode)
        if block is None:
            return None
    else:
        block = _name_window(text, name)
        if not block:
            return None
        pc = ""
    nt = discover.tokens(name)
    if nt and not any(w in block.lower() for w in nt):
        if not (pc and pc in block.upper().replace(" ", "")):
            return None
    if discover.CLOSED.search(block):
        return None
    got = discover.extract_times(block, None)
    if not got:
        return None
    raw = (got.get("quote") or got.get("raw") or "").strip()
    if not raw or not CLOCK.search(raw) or not DAYW.search(raw):
        return None
    return re.sub(r"\s+", " ", raw)[:240]


def needs_follow(url, text, name, postcode):
    """True when this landing page is a generic council/organisation page with no weekday+time for the venue."""
    url = normalise_website(url)
    if not discover.usable_site(url) or _directory(url):
        return False
    if quote_for_venue(text or "", name, postcode):
        return False
    many = len(discover.find_pcs(text or "")) >= 3
    if many:
        return True
    if _gov(url):
        return True
    if _index_path(url) and not host_shares_name(url, name):
        return True
    if host_shares_name(url, name):
        return False
    return True


def _record(c, kind, evidence_url, quote, found_via, day):
    row = {
        "passed": True,
        "id": c.get("id"),
        "layer": LAYER.get(kind, kind),
        "name": c.get("name") or "",
        "postcode": c.get("postcode") or "",
        "address": c.get("address") or "",
        "evidence_url": evidence_url,
        "day_time_quote": quote,
        "source_url": c.get("source_url") or c.get("directory_url") or "",
        "website": normalise_website(c.get("website")),
        "found_via": found_via,
        "checked_on": day or "",
        "rule": "official or own page states a weekday and a time",
    }
    if c.get("lat") is not None and c.get("lng") is not None:
        row["lat"], row["lng"] = c["lat"], c["lng"]
    for k in PHONE_KEYS:
        row.pop(k, None)
    return row


class Budget:
    """One gap between requests to a host, a per-host cap, and an in-run cache."""

    def __init__(self, fetcher, per_host=8, gap=None, sleep=None, render=False):
        self.fetcher = fetcher
        self.per_host = per_host
        self.gap = float(os.environ.get("FOLLOW_GAP", "1")) if gap is None else gap
        self.sleep = time.sleep if sleep is None else sleep
        self.render = render
        self.cache = {}
        self.counts = {}
        self.last = {}
        self.lock = threading.Lock()

    def fetch(self, url):
        url = normalise_website(url)
        with self.lock:
            if url in self.cache:
                return self.cache[url]
            h = discover.host(url)
            n = self.counts.get(h, 0)
            wait = self.gap - (time.time() - self.last.get(h, 0)) if n else 0
        if n >= self.per_host:
            return {"http": "skipped", "final_url": url, "html": "", "reason": "host budget"}
        if wait > 0:
            self.sleep(wait)
        with self.lock:
            if url in self.cache:
                return self.cache[url]
            if self.counts.get(h, 0) >= self.per_host:
                return {"http": "skipped", "final_url": url, "html": "", "reason": "host budget"}
            self.counts[h] = self.counts.get(h, 0) + 1
            self.last[h] = time.time()
        try:
            res = self.fetcher(url) or {}
        except Exception as ex:
            res = {"http": "error", "final_url": url, "html": "", "error": str(ex)[:120]}
        if "html" not in res and res.get("text"):
            res = dict(res, html=res.get("text") or "")
        res = self._render(url, res)
        with self.lock:
            self.cache[url] = res
        return res

    def _render(self, url, res):
        fn = self.render
        if fn is False or fn is None:
            return res
        if not callable(fn):
            fn = default_render if render_enabled() else None
        if not fn:
            return res
        if res.get("http") != 200 or len(discover.text_of(res.get("html") or "")) >= 200:
            return res
        h = discover.host(url)
        with self.lock:
            if self.counts.get(h, 0) >= self.per_host:
                return res
            self.counts[h] = self.counts.get(h, 0) + 1
        try:
            got = fn(url)
        except Exception:
            return res
        if isinstance(got, tuple) and len(got) >= 3 and got[2]:
            code, final, html = got[0], got[1], got[2]
            if len(discover.text_of(html)) > len(discover.text_of(res.get("html") or "")):
                return {"http": code or 200, "final_url": final or url, "html": html, "rendered": True}
        return res


def _same_site(a, b):
    ha, hb = discover.host(a), discover.host(b)
    return bool(ha) and (ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha))


def _score(url, anchor, name, postcode):
    blob = ((url or "") + " " + (anchor or "")).lower()
    score = sum(3 for w in discover.tokens(name) if w in blob)
    pc = discover.norm_pc(postcode).lower()
    if pc and pc in re.sub(r"\s+", "", blob):
        score += 5
    return score


def _links(html, page_url, name, postcode, limit=3):
    found = []
    for href, anchor in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html or "", re.I | re.S):
        if href.startswith(("mailto:", "tel:", "javascript:")) or ASSET.search(href):
            continue
        u = urllib.parse.urljoin(page_url, href.split("#")[0])
        if not _same_site(u, page_url) or discover.host(u) != discover.host(page_url) and not _same_site(u, page_url):
            continue
        if not _same_site(u, page_url):
            continue
        sc = _score(u, discover.text_of(anchor), name, postcode)
        if sc > 0 and u.rstrip("/") != (page_url or "").rstrip("/"):
            found.append((sc, u))
    found.sort(key=lambda x: -x[0])
    out, seen = [], set()
    for sc, u in found:
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
        if len(out) >= limit:
            break
    return out


def _sitemap_urls(xml, page_url, name, postcode, limit=3):
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml or "")[:2000]
    kids = [u for u in locs if u.lower().endswith(".xml") or "sitemap" in u.lower()]
    pages = [u for u in locs if u not in kids and _same_site(u, page_url)]
    ranked = sorted((( _score(u, u, name, postcode), u) for u in pages), key=lambda x: -x[0])
    return [u for sc, u in ranked if sc > 0][:limit], [u for u in kids if _same_site(u, page_url)][:2]


def _search_url(html, page_url, name):
    m = re.search(r'<form[^>]*action="([^"]*)"[^>]*>(.*?)</form>', html or "", re.I | re.S)
    if not m:
        return None
    action, inner = m.group(1), m.group(2)
    if not re.search(r'type="search"|name="(?:q|s|search|query)"', inner, re.I):
        return None
    fm = re.search(r'name="(q|s|search|query)"', inner, re.I)
    field = fm.group(1) if fm else "q"
    action_u = urllib.parse.urljoin(page_url, action or "")
    if not _same_site(action_u, page_url):
        return None
    q = urllib.parse.urlencode({field: name})
    return action_u + ("&" if "?" in action_u else "?") + q


def _page_text(res):
    if not res:
        return ""
    if res.get("html"):
        return discover.text_of(res["html"])
    return res.get("text") or ""


def _pass_on(c, kind, res, found_via, day, home):
    if not res or res.get("reason") == "host budget":
        return None
    final = res.get("final_url") or ""
    if final and not _same_site(final, home):
        return None
    q = quote_for_venue(_page_text(res), c.get("name"), c.get("postcode"))
    if not q:
        return None
    return _record(c, kind, final or home, q, found_via, day)


def follow(c, kind, budget, day=None, landing=None):
    """Find weekday+time for this venue on its own page on the same site. Does not publish."""
    url = normalise_website(c.get("website"))
    if not discover.usable_site(url) or any(s in url for s in SKIP_PARTS):
        return {"passed": False, "reason": "no usable website"}
    res = landing
    if res is None:
        res = budget.fetch(url)
        if res.get("reason") == "host budget":
            return {"passed": False, "reason": "host budget", "retry": True}
    landed = res.get("final_url") or url
    if not _same_site(landed, url):
        return {"passed": False, "reason": "page left the site"}
    home = landed
    text = _page_text(res)
    direct = _pass_on(c, kind, res, "direct", day, url)
    if direct:
        return direct
    if not needs_follow(home, text, c.get("name"), c.get("postcode")):
        return {"passed": False, "reason": "not a generic council or organisation page"}
    html = res.get("html") or ""
    tried = [("link", u) for u in _links(html, home, c.get("name"), c.get("postcode"))]
    su = _search_url(html, home, c.get("name") or "")
    if su:
        tried.append(("search", su))
    origin = urllib.parse.urlparse(home)
    sm_url = urllib.parse.urlunparse((origin.scheme or "https", origin.netloc, "/sitemap.xml", "", "", ""))
    sm = budget.fetch(sm_url)
    budget_hit = sm.get("reason") == "host budget"
    if not budget_hit:
        pages, kids = _sitemap_urls(sm.get("html") or "", home, c.get("name"), c.get("postcode"))
        tried += [("sitemap", u) for u in pages]
        for kid in kids:
            child = budget.fetch(kid)
            if child.get("reason") == "host budget":
                budget_hit = True
                break
            more, _ = _sitemap_urls(child.get("html") or "", home, c.get("name"), c.get("postcode"))
            tried += [("sitemap", u) for u in more]
    seen = set()
    for via, u in tried:
        if u in seen:
            continue
        seen.add(u)
        page = budget.fetch(u)
        if page.get("reason") == "host budget":
            budget_hit = True
            continue
        hit = _pass_on(c, kind, page, via, day, home)
        if hit:
            return hit
    if budget_hit:
        return {"passed": False, "reason": "host budget", "retry": True}
    return {"passed": False, "reason": "no venue page with a weekday and a time"}


def consider(c, check, decision, kind, budget, day):
    """Proposal only. Never changes the discovery add/flag decision."""
    if kind not in ("ws", "sh"):
        return None
    url = normalise_website(c.get("website"))
    if not discover.usable_site(url):
        return None
    text = (check or {}).get("_text") or ""
    if text and quote_for_venue(text, c.get("name"), c.get("postcode")):
        final = (check or {}).get("final_url") or url
        if _same_site(final, url) or _gov(url):
            return _record(c, kind, final, quote_for_venue(text, c.get("name"), c.get("postcode")), "direct", day)
    if text and not needs_follow(url, text, c.get("name"), c.get("postcode")):
        return None
    if not text and not needs_follow(url, text, c.get("name"), c.get("postcode")):
        return None
    return follow(c, kind, budget, day)


def to_place(hit):
    place = {k: hit[k] for k in STORE if hit.get(k) not in (None, "")}
    for k in PHONE_KEYS:
        place.pop(k, None)
    return place


def merge_proposal(hits, root, day):
    """Merge verified places into the review file. Does not touch the allowlist or the map."""
    places = [to_place(h) for h in hits or [] if h and h.get("passed") and h.get("id") and h.get("evidence_url") and h.get("day_time_quote")]
    if not root or not places:
        return None
    path = os.path.join(root, PROPOSAL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        cur = json.load(open(path, encoding="utf-8"))
    except Exception:
        cur = {}
    by = {p.get("id"): p for p in (cur.get("places") or []) if p.get("id")}
    for p in places:
        by[p["id"]] = p
    out = {
        "generated": day or cur.get("generated") or "",
        "rule": "21 Oct 2026: a place is published only when an official or own page states a weekday and a time. "
                "This file is a proposal for a reviewed PR. It does not publish, and it does not change phones or council lines.",
        "places": [by[k] for k in sorted(by)],
    }
    tmp = path + ".tmp"
    json.dump(out, open(tmp, "w"), indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def _load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def sweep_held(root=None, fetcher=None, limit=40, gap=1.0, render=None, day=None):
    """Bounded pass over held warm spaces and shelters. Writes the proposal; publishes nothing."""
    import datetime
    root = root or ROOT
    day = day or datetime.date.today().isoformat()
    fetcher = fetcher or discover.fetch_raw
    if render is None:
        render = default_render if render_enabled() else False
    seen_path = os.path.join(root, SEEN)
    seen = _load_json(seen_path, {})
    if not isinstance(seen, dict):
        seen = {}
    rows = []
    for layer, fn in (("warmspaces", "warmspaces_pending.json"), ("shelters", "shelters_pending.json")):
        kind = "ws" if layer == "warmspaces" else "sh"
        for row in _load_json(os.path.join(root, "logs", fn), []):
            if not isinstance(row, dict):
                continue
            rows.append(dict(row, _kind=kind, _layer=layer))
    todo = [r for r in rows if r.get("id") and r["id"] not in seen and discover.usable_site(normalise_website(r.get("website")))]
    todo = todo[:limit]
    budget = Budget(fetcher, per_host=int(os.environ.get("FOLLOW_PER_HOST", "8")), gap=gap, render=render)
    hits, checked = [], []
    for r in todo:
        try:
            hit = follow(r, r["_kind"], budget, day)
        except Exception as ex:
            hit = {"passed": False, "reason": str(ex)[:80]}
        if not hit.get("retry"):
            seen[r["id"]] = day
            checked.append(r["id"])
        if hit.get("passed"):
            hits.append(hit)
    os.makedirs(os.path.dirname(seen_path), exist_ok=True)
    json.dump(seen, open(seen_path, "w"), indent=0)
    path = merge_proposal(hits, root, day)
    return {"checked": len(checked), "passed": len(hits), "proposal": path, "examples": [to_place(h) for h in hits[:8]]}


def dry_run(root=None, sample=200, fetcher=None, gap=1.0, render=False, day=None, out_path=None):
    """Follow-through on a deterministic sample of held warm spaces. Does not publish or write the proposal."""
    import datetime
    root = root or ROOT
    day = day or datetime.date.today().isoformat()
    fetcher = fetcher or discover.fetch_raw
    pending = _load_json(os.path.join(root, "logs", "warmspaces_pending.json"), [])
    usable = [r for r in pending if isinstance(r, dict) and discover.usable_site(normalise_website(r.get("website")))]
    if len(usable) > sample:
        step = max(1, len(usable) // sample)
        picked = usable[::step][:sample]
    else:
        picked = usable[:sample]
    budget = Budget(fetcher, per_host=int(os.environ.get("FOLLOW_PER_HOST", "8")), gap=gap, render=render)
    passed, failed, skipped = [], [], 0

    def one(r):
        try:
            return r, follow(dict(r), "ws", budget, day)
        except Exception as ex:
            return r, {"passed": False, "reason": str(ex)[:80]}
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(int(os.environ.get("FOLLOW_THREADS", "6"))) as ex:
        results = list(ex.map(one, picked))
    for r, hit in results:
        if hit.get("retry"):
            skipped += 1
        elif hit.get("passed"):
            passed.append(to_place(hit))
        else:
            failed.append({"id": r.get("id"), "name": r.get("name"), "website": normalise_website(r.get("website")), "reason": hit.get("reason")})
    from collections import Counter
    report = {
        "day": day,
        "pending": len(pending),
        "usable_websites": len(usable),
        "sample": len(picked),
        "sample_rule": "even stride across held warm spaces that have a usable website",
        "passed": len(passed),
        "failed": len(failed),
        "host_budget_skipped": skipped,
        "places": passed,
        "examples": passed[:12],
        "fail_reason_counts": dict(Counter(f.get("reason") or "" for f in failed)),
        "fail_reasons": failed[:12],
    }
    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        json.dump(report, open(out_path, "w"), indent=1, ensure_ascii=False)
    return report


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "sweep-held":
        print(json.dumps(sweep_held(), default=str)[:2000])
        return 0
    if cmd == "dry-run":
        n = int(argv[2]) if len(argv) > 2 else 200
        out = argv[3] if len(argv) > 3 else ""
        rep = dry_run(sample=n, out_path=out or None, render=default_render if render_enabled() else False)
        print(json.dumps({k: rep[k] for k in ("sample", "passed", "failed", "host_budget_skipped", "usable_websites")}, indent=1))
        return 0
    print("usage: follow_through.py sweep-held | dry-run [N] [out.json]")
    return 0


if __name__ == "__main__":
    import sys
    try:
        sys.exit(main(sys.argv))
    except Exception as ex:
        print("follow-through failed: %s" % ex)
        sys.exit(0)
