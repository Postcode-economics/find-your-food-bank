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
overrides/opening_times.json ONLY when strict AND times_auto_apply is on (see decide(), strict_checks()); all else -> reports/pending_dean.md; the normal refresh then re-confirms them on the own site every run (cross_check_times)."""
import json, os, re, sys, time, threading, subprocess, tempfile, urllib.parse, datetime, collections, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_rules; RULES = auto_rules.load()  # Dean 25 Oct 2026: refresh stops if overrides/auto_apply_rules.json is missing
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
            pcs = [norm_pc(i.get("postcode"))] if i.get("postcode") and norm_pc(i.get("postcode")) in dict(pages).get(u, "").upper().replace(" ", "") else []
            ot = dict(ot, source_url=u, checked_date=RUN, reader="times_finder", pc_seen=pcs); out[i["id"]] = (ot, "found on own site")
        else: out[i["id"]] = (None, "no client times found on own site (home, sitemap and %d linked pages read)" % (len(pages) - 1))
    return out
KNOWN = os.path.join(os.path.dirname(__file__), "..", "overrides", "known_sources.json")
def known():
    try: return json.load(open(KNOWN))
    except Exception: return {"pages": {}, "skip": {}}
def skipped(iid, ks):
    for k, v in ks.get("skip", {}).items():
        if iid == k or (k.endswith("/*") and iid.startswith(k[:-1])) or (k.endswith("/*") and iid == k[:-2]): return v["reason"]
    return None
def own_page(ot, item):
    u = urllib.parse.urlparse(ot.get("source_url") or "").netloc.lower().removeprefix("www.")
    w = urllib.parse.urlparse(item.get("website") or "").netloc.lower().removeprefix("www.")
    return bool(u and w and (u == w or u.endswith("." + w) or w.endswith("." + u)))
def one_block(ot):
    """One clear client-hours block: parsed into a weekly table, no qualifiers, not office-like."""
    return ot.get("status") == "TIMES_FOUND" and bool(ot.get("structured")) and not D.office_like(ot["structured"])
DONATION_URL = re.compile(r"donat|giv(e|ing)|volunteer|drop-?off|support-us|fundrais", re.I)   # Hope Central /get-involved/giving-food/ (24 Oct)
TIMES_KEY = "times_auto_apply"   # overrides/auto_apply_rules.json; missing = OFF
SEEN = "logs/times_finder_seen.json"            # last run's parsed times per id (for the 2-run rule)
AUTO_LOG = "reports/times_auto_applied.json"    # every automatic change, revert with scripts/times_revert.py <id>
UNDONE = "overrides/times_auto_undone.json"     # 'finder:<id>' -> parsed table Dean undid (times_revert.py); never re-applied
def undone_key(k): return "finder:" + k
def times_auto_on(rules=None): return bool((rules if rules is not None else RULES).get(TIMES_KEY, False))
def _sig(ot): return json.dumps(ot.get("structured"), sort_keys=True) if ot and ot.get("structured") else None
def _empty(ot):
    """No usable times: missing, closed, all-closed, or a weekly table with no sessions."""
    if not ot: return True
    if isinstance(ot, dict) and ot.get("all_closed"): return True
    if str(ot.get("status", "")).upper() in ("CLOSED", "NO_TIMES", "") : return True
    st = ot.get("structured")
    if st is not None and not any(v for v in st.values()): return True
    return not (st or (ot.get("raw") or "").strip())
def strict_checks(k, ot, it, cur, seen, same_n, ks, blocked=None):
    """Reasons a finder result must stay held for Dean. Empty list = it may auto-apply (only if times_auto_apply is ON).
    Each safeguard blocks on its own (tests/test_times_auto_apply.py). blocked: overrides/times_auto_undone.json."""
    why = []
    if (cur.get(k) or {}).get("protected"): why.append("hand-checked times are protected; finder only flags differences")
    r = skipped(k, ks)
    if r: why.append("known skip: " + r)
    pc_ok = ot.get("matched_by") == "postcode" or (it.get("postcode") and norm_pc(it["postcode"]) in (ot.get("pc_seen") or []))
    if not pc_ok: why.append("postcode not matched exactly on the page")
    if not one_block(ot): why.append("not one clear weekly client-hours block (kept as text for review)")
    if not own_page(ot, it) and ot.get("reader") != "trussell_cards": why.append("not on the food bank's own site")
    if DONATION_URL.search(urllib.parse.urlparse(ot.get("source_url") or "").path): why.append("source page is about giving/donating, not getting food")
    if same_n > 1: why.append("identical times read for several centres with different postcodes (possible copy)")
    prev = (seen or {}).get(k) or {}
    if (not _sig(ot) or prev.get("sig") != _sig(ot) or prev.get("source_url") != ot.get("source_url")
            or not prev.get("run_at") or prev.get("run_at") == ot.get("_run_at")):
        why.append("times not read identically on 2 separate runs yet")
    if _sig(ot) and not _empty(ot) and not D.day_same_line(ot.get("structured"), [ot.get("raw") or ""]):
        why.append("day not on the same line as its times on the own-site page")
    old = cur.get(k) or it.get("opening_times")
    if old and not _empty(old) and _empty(ot): why.append("would change known times to closed/empty")
    # Hours only. A different phone on the stored listing is not a source conflict (that fix stays held on the phone path).
    # Known times kept as text (no table) from another source are known times too, so they conflict with any new table.
    if old and not _empty(old) and _sig(old) != _sig(ot) and (old.get("source_url") or "") != (ot.get("source_url") or ""):
        why.append("conflicts with times from another source (%s)" % (old.get("source_url") or "unknown"))
    if _sig(ot) and (blocked or {}).get(undone_key(k)) == _sig(ot): why.append("this change was undone by Dean; not re-applied")
    return why
def _read(ot):
    """A times result was actually read. No table, no text and no explicit closed status means nothing was found."""
    if not isinstance(ot, dict): return False
    if ot.get("structured") is not None: return True
    if str(ot.get("status") or "").upper() == "CLOSED": return True
    return bool((ot.get("raw") or "").strip())
def decide(log, items, apply, rules=None, now=None):
    """Dean, 23 Oct 23:36: nothing uncertain goes on the map. Dean, 27 Oct: times auto-apply ONLY when every strict_checks()
    safeguard passes AND overrides/auto_apply_rules.json has times_auto_apply true. Everything else -> reports/pending_dean.md."""
    on = times_auto_on(rules); now = now or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    ix = {i["id"]: i for i in items}; ks = known()
    p = "overrides/opening_times.json"; cur = json.load(open(p)) if os.path.exists(p) else {}
    seen = json.load(open(SEEN)) if os.path.exists(SEEN) else {}
    blocked = json.load(open(UNDONE)) if os.path.exists(UNDONE) else {}
    same = collections.defaultdict(set)
    for k, ot in log["found"].items():
        same[(urllib.parse.urlparse(ot.get("source_url") or "").netloc, ot.get("raw"))].add(norm_pc(ix.get(k, {}).get("postcode")))
    log["applied"], log["review"] = [], []
    auto = json.load(open(AUTO_LOG)) if os.path.exists(AUTO_LOG) else []
    new_seen = {}
    for k, ot in sorted(log["found"].items()):
        # Dean 27 Oct 2026 12:12 GMT: nothing read. Leave the stored listing untouched and do not queue a pending row.
        if not _read(ot): continue
        it = ix.get(k, {}); ot = dict(ot, _run_at=now)
        why = strict_checks(k, ot, it, cur, seen, len(same[(urllib.parse.urlparse(ot.get("source_url") or "").netloc, ot.get("raw"))]), ks, blocked)
        if not why and not on: why.append("times auto-apply is off (overrides/auto_apply_rules.json times_auto_apply): hand check first")
        if _sig(ot): new_seen[k] = {"sig": _sig(ot), "source_url": ot.get("source_url"), "run_at": now}
        if why: log["review"].append({"id": k, "name": it.get("name"), "postcode": it.get("postcode"), "proposed": ot.get("raw"), "source_url": ot.get("source_url"), "why": why})
        else:
            clean = {x: v for x, v in ot.items() if not x.startswith("_")}
            dup = any(e.get("id") == k and not e.get("path") and not e.get("reverted") and (e.get("new") or {}).get("structured") == clean.get("structured")
                      and e.get("source_url") == clean.get("source_url") for e in auto)
            if not dup:
                auto.append({"id": k, "name": it.get("name"), "old": cur.get(k) or it.get("opening_times"), "new": clean, "source_url": ot.get("source_url"),
                             "first_run_at": seen[k]["run_at"], "second_run_at": now, "revert": "python scripts/times_revert.py " + k})
            cur[k] = clean; log["applied"].append(k)
    json.dump(log, open("logs/times_finder.json", "w"), indent=0, ensure_ascii=False)
    os.makedirs("logs", exist_ok=True); json.dump(new_seen, open(SEEN, "w"), indent=0, sort_keys=True, ensure_ascii=False)
    if log["applied"]:
        json.dump(cur, open(p, "w"), indent=1, sort_keys=True, ensure_ascii=False)
        os.makedirs("reports", exist_ok=True); json.dump(auto, open(AUTO_LOG, "w"), indent=1, ensure_ascii=False)
    os.makedirs("reports", exist_ok=True)
    pd = "reports/pending_dean.md"; prev = open(pd).read() if os.path.exists(pd) else ""
    prev = re.sub(r"(?s)\n*<!-- times review -->.*?<!-- /times review -->\n*", "\n", prev).rstrip("\n")
    if log["review"] or log["applied"]:
        L = ["<!-- times review -->", "## Opening-times review list (times_finder)", "", f"Run {RUN}. AUTO-APPLIED rows are on the map (strict gate, 2 identical runs; each has its undo command). "
             "Every other row is not on the map and needs a hand check before it is added.", ""]
        for k in log["applied"]:
            L.append(f"- AUTO-APPLIED `{k}` (strict, 2 identical runs). Undo: `python scripts/times_revert.py {k}`")
        for r in log["review"]:
            L.append(f"- **{r['name']}** (`{r['id']}`, {r['postcode']}): {r['proposed']}  \n  source: {r['source_url']}  \n  why: {'; '.join(r['why'])}")
        L.append("<!-- /times review -->")
        if not prev.strip(): prev = "# Pending for Dean"
        open(pd, "w").write(prev + "\n\n" + "\n".join(L) + "\n")
    elif prev.strip():
        open(pd, "w").write(prev + "\n")
    elif os.path.exists(pd):
        os.remove(pd)
def norm_pc(pc): return re.sub(r"\s", "", (pc or "").upper())
def run(items, apply=False, threads=12, render=None, now=None):
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
            if not cards and render:  # new Trussell sites draw the centre cards with JavaScript: render them headless
                cards = TT.site_cards(base, fetcher=render)
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
    decide(log, items, apply, now=now)
    return log
if __name__ == "__main__":
    src = sys.argv[sys.argv.index("--data") + 1] if "--data" in sys.argv else "data.full.js"
    s = open(src).read(); items = json.loads(s[s.index("{"): s.rindex("}") + 1])["items"]
    if "--only" in sys.argv: items = [i for i in items if i.get("network") == sys.argv[sys.argv.index("--only") + 1]]
    rf = None
    if "--render" in sys.argv:
        import render_fetch; rf = render_fetch.fetch
    l = run(items, apply="--apply" in sys.argv, render=rf)
    print(len(l.get("applied", [])), "auto-applied (strict);", len(l.get("review", [])), "sent to reports/pending_dean.md")
    print(l["checked"], "checked;", len(l["found"]), "times found")
