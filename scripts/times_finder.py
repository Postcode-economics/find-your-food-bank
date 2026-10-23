"""Raise food bank opening-times coverage (entries with no opening_times). Conservative: never guess.
1. Trussell (*.foodbank.org.uk): read the centre cards (scripts/trussell_times.py).
2. Everyone else: own site home + sitemap.xml + up to 10 same-site pages whose link/URL says opening/times/
   when/contact/find-us/get-help/centres/locations/visit, plus linked PDFs (pdftotext if installed).
   Times are taken only from a page that shows THIS entry's postcode (multi-branch pages: the block around the
   postcode, via discover.extract_times), or - for a single-centre food bank - from a times page of its own site.
   Office / donation / warehouse hours are skipped. Anything that doesn't parse cleanly is kept 'as written'
   (TIMES_TEXT_ONLY). Facebook / Instagram need a login, so they are not read.
3. Retries with backoff for unreachable sites; 1 s between requests to the same host.
Output: logs/times_finder.json (proposals + reasons). With --apply, proposals are added to
overrides/opening_times.json; the normal refresh then re-confirms them on the own site every run (cross_check_times)."""
import json, os, re, sys, time, threading, subprocess, tempfile, urllib.parse, datetime, collections, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(__file__))
import trussell_times as TT
import discover as D
RUN = datetime.date.today().isoformat()
LINKW = re.compile(r"open|time|hour|when|contact|find|get-?help|need-?help|centre|center|location|visit|where|distribution|session", re.I)
SOCIAL = re.compile(r"facebook\.com|instagram\.com|twitter\.com|x\.com/|linktr\.ee", re.I)
_last, _locks = {}, collections.defaultdict(threading.Lock)
def polite(url, tries=3):
    h = urllib.parse.urlparse(url).netloc
    with _locks[h]:
        w = 1.0 - (time.time() - _last.get(h, 0))
        if w > 0: time.sleep(w)
        r = TT.fetch(url, tries)
        _last[h] = time.time()
    return r
def pdf_text(url):
    code, _, _ = 0, 0, 0
    try:
        import urllib.request
        b = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=25).read(5_000_000)
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(b); f.flush()
            return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=30).stdout
    except Exception: return ""
OLDTPL = re.compile(r"Opening days? ((?:(?:mon|tues|wednes|thurs|fri|satur|sun)day[s]?\s*(?:,|&|and)?\s*)+)Opening (?:hours|times) ", re.I)
def fix_text(t):  # old Trussell WordPress template: 'Opening day Thursday Opening hours 1:30pm - 3:00pm'
    return OLDTPL.sub(lambda m: m.group(1).strip() + " ", t)
def site_texts(base, maxpages=10):
    code, final, h = polite(base)
    if code != 200 or not h: return code, final, []
    pages = [(final, fix_text(TT.text_of(h)))]; links = []
    for m in re.findall(r'href="([^"#]+)"', h):
        u = urllib.parse.urljoin(final, m)
        if urllib.parse.urlparse(u).netloc == urllib.parse.urlparse(final).netloc and LINKW.search(m) and u not in links and u != final: links.append(u)
    c2, _, sm = polite(urllib.parse.urljoin(final, "/sitemap.xml"), tries=1)
    if c2 == 200:
        for u in re.findall(r"<loc>([^<]+)</loc>", sm):
            if LINKW.search(urllib.parse.urlparse(u).path) and u not in links and not u.endswith(".xml"): links.append(u)
    loc = [u for u in links if "/location/" in u]  # Trussell WordPress: one page per centre, read them all
    for u in loc + [u for u in links if u not in loc][:maxpages]:
        if u.lower().endswith(".pdf"): t = pdf_text(u)
        else:
            c, f, hh = polite(u); t = TT.text_of(hh) if c == 200 else ""
        if t: pages.append((u, fix_text(t)))
    return code, final, pages
def generic(items_for_site, base):
    code, final, pages = site_texts(base)
    out = {}
    if not pages:
        for i in items_for_site: out[i["id"]] = (None, f"own site unreachable (HTTP {code}) after 3 tries")
        return out
    single = len(items_for_site) == 1
    for i in items_for_site:
        best = None
        for u, t in pages:
            ot = D.extract_times(t, i.get("postcode"))
            if ot: best = (u, ot); break
        if not best and single:
            for u, t in pages[1:]:
                if re.search(r"open|times|when", u, re.I):
                    ot = D.extract_times(t, None)
                    if ot: best = (u, ot); break
        if best:
            u, ot = best
            if ot.get("structured") and D.office_like(ot["structured"]): out[i["id"]] = (None, "times found look like office hours; skipped"); continue
            ot = dict(ot, source_url=u, checked_date=RUN, reader="times_finder"); out[i["id"]] = (ot, "found on own site")
        else: out[i["id"]] = (None, "no client times found on own site (home, sitemap and %d linked pages read)" % (len(pages) - 1))
    return out
def run(items, apply=False, threads=12):
    todo = [i for i in items if not (i.get("opening_times") or {}).get("status") and i.get("kind") != "warehouse"]
    by = collections.defaultdict(list)
    for i in todo:
        w = (i.get("website") or "").strip()
        by[w].append(i)
    res = {}
    def one(w):
        its = by[w]
        if not w or not w.startswith("http"): return {i["id"]: (None, "no own website") for i in its}
        if SOCIAL.search(w): return {i["id"]: (None, "only a social media page (needs login; not read)") for i in its}
        host = urllib.parse.urlparse(w).netloc
        if host.endswith(".foodbank.org.uk"):
            base = "https://" + host
            cards = TT.site_cards(base, fetcher=polite)
            if not cards:  # older Trussell template: fall back to the generic own-site reader
                o = generic(its, w)
                return {k: (v[0], v[1] if v[0] else "Trussell site: no centre cards at " + TT.PATH + "; " + v[1]) for k, v in o.items()}
            o = {}
            for i in its:
                c, how = TT.match(i, cards)
                ot = TT.to_ot(c, c["url"], RUN) if c else None
                o[i["id"]] = (dict(ot, matched_by=how, card_name=c["name"]) if ot else None, ("found on Trussell centre card (" + how + ")") if ot else (how if not c else "card lists every day as Closed"))
            return o
        return generic(its, w)
    with cf.ThreadPoolExecutor(threads) as ex:
        for r in ex.map(one, list(by)): res.update(r)
    log = {"run": RUN, "checked": len(todo), "found": {k: v[0] for k, v in res.items() if v[0]}, "reasons": {k: v[1] for k, v in res.items()}}
    os.makedirs("logs", exist_ok=True)
    json.dump(log, open("logs/times_finder.json", "w"), indent=0, ensure_ascii=False)
    if apply:
        p = "overrides/opening_times.json"; cur = json.load(open(p))
        # Auto-apply only the robust readers: Trussell centre cards and one-page-per-centre Trussell /location/ pages.
        # Everything else (multi-branch prose, venue pages) is listed in logs/times_finder.json "review" for Dean.
        for k, ot in log["found"].items():
            if ot.get("reader") == "trussell_cards" or "/location/" in (ot.get("source_url") or ""): cur.setdefault(k, ot)
            else: log.setdefault("review", []).append(k)
        json.dump(log, open("logs/times_finder.json", "w"), indent=0, ensure_ascii=False)
        json.dump(cur, open(p, "w"), indent=1, ensure_ascii=False, sort_keys=True)
    return log
if __name__ == "__main__":
    src = sys.argv[sys.argv.index("--data") + 1] if "--data" in sys.argv else "data.full.js"
    s = open(src).read(); items = json.loads(s[s.index("{"): s.rindex("}") + 1])["items"]
    if "--only" in sys.argv: items = [i for i in items if i.get("network") == sys.argv[sys.argv.index("--only") + 1]]
    l = run(items, apply="--apply" in sys.argv)
    print(l["checked"], "checked;", len(l["found"]), "times found")
