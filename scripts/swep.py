"""SWEP (Severe Weather Emergency Protocol) watcher. Runs with the shelters refresh.
* Source list: overrides/swep_sources.json ({"council", "url"}), kept up to date by discover() during the
  overnight sweep: each council site in scripts/sweep_sources.json is scanned (homepage + known pages, 1-2
  requests per council, polite) for links about SWEP / severe weather / rough sleeping.
* Every run: fetch each SWEP page and classify it from the council's own wording: active / not active / unknown.
  Writes logs/swep_status.json and lists changes (activated / deactivated) for Dean's daily review.
Nothing here changes the map: SWEP is reached through outreach/StreetLink, not a walk-in address, so it is
flagged for review, never auto-pinned."""
import json, os, re, sys, datetime, concurrent.futures as cf, urllib.parse, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import auto_rules; RULES = auto_rules.load()  # Dean 25 Oct 2026: refresh stops if overrides/auto_apply_rules.json is missing
sys.path.insert(0, os.path.dirname(__file__))
from page_visible import html_to_visible_text
SRC, LOG = "overrides/swep_sources.json", "logs/swep_status.json"
KW = re.compile(r"\bSWEP\b|severe weather emergency|severe weather protocol|cold weather (shelter|provision|protocol)", re.I)
ON = re.compile(r"(SWEP|severe weather emergency protocol|severe weather protocol|cold weather provision)[^.]{0,80}?\b(is (now |currently )?(active|activated|in place|in operation|open|running)|has been (activated|triggered|implemented)|(will be|has been) put in place)(?! (when|if|during|whenever))", re.I)
OFF = re.compile(r"(SWEP|severe weather emergency protocol|severe weather protocol)[^.]{0,80}?\b(is (not|no longer) (currently )?(active|in place|in operation)|:\s*not active|has been (de-?activated|stood down|lifted|ended)|is currently inactive|stood down)", re.I)
LINK = re.compile(r'href="([^"#]+)"[^>]*>([^<]{0,140})<', re.I)
LINKWORDS = re.compile(r"swep|severe[- ]weather|rough[- ]sleep|cold[- ]weather|winter[- ]shelter|night[- ]shelter", re.I)
def classify_html(html, run_day=None):
    """Classify SWEP status from council HTML (comments and hidden blocks stripped first)."""
    return classify(html_to_visible_text(html), run_day)
def classify(text, run_day=None):
    """Return (status, quote) from visible plain text. The LATEST-mentioned state on the page wins when both appear."""
    t = re.sub(r"\s+", " ", text or "")
    if not KW.search(t): return "no SWEP wording", ""
    cond = lambda m: re.search(r"\b(when|if|whenever|until)\s+$", t[max(0, m.start() - 12):m.start()], re.I) or re.match(r"\s*(when|if)\b", t[m.end():m.end() + 8], re.I)
    # 24 Oct 2026 (Durham false active): ignore activations stated conditionally anywhere in the same sentence
    # ("updated if SWEP is activated", "When the temperature reaches 0C ... is activated", "During spells ... is activated").
    CONDW = re.compile(r"\b(if|when|whenever|during|once|until|as soon as|in the event|in periods of|under these conditions|will be updated)\b", re.I)
    sent = lambda m: t[max(t.rfind(". ", 0, m.start()) + 1, m.start() - 200, 0): m.end()]
    # 24 Oct 2026 11:45 (Dean): general descriptions ("has been put in place", "is in place to support") are NOT active.
    # Active only when the page clearly says SWEP is on now: "currently active", "now active", "open tonight", "activated from <date>".
    NOW = re.compile(r"\b(currently|now|tonight|today|this (evening|week|weekend)|with immediate effect)\b|\bfrom (\d{1,2}(st|nd|rd|th)? \w+|(mon|tues|wednes|thurs|fri|satur|sun)day|\d{1,2}[/.]\d{1,2})", re.I)
    near = lambda m: "" if re.match(r"\s*to (support|help|protect|ensure|prevent)\b", t[m.end():m.end() + 20], re.I) else m.group(0) + t[m.end():m.end() + 30]   # "in place to support ..." = general description
    on = [m for m in ON.finditer(t) if not cond(m) and not CONDW.search(sent(m)) and (NOW.search(near(m)) or re.search(r"has been (activated|triggered)", m.group(0), re.I))]
    off = [m for m in OFF.finditer(t) if not cond(m)]   # 'has been activated/triggered' = a specific notice; old ones caught by the date check below
    if not on and not off: return "unknown", ""
    last_on = on[0] if on else None; last_off = off[0] if off else None  # first mention = page headline / latest news
    if last_on and (not last_off or last_on.start() < last_off.start()): m, st = last_on, "active"
    else: m, st = last_off, "not active"
    q = t[max(0, m.start() - 60): m.end() + 80]
    if st == "active" and run_day:
        import seasonal
        ds = [d for d in seasonal._all(t) if d.isoformat() <= run_day]
        if ds and (datetime.date.fromisoformat(run_day) - max(ds)).days > 10:
            return "old notice (latest date on page %s)" % max(ds).isoformat(), q
    return st, q
def in_season(md, frm, to):
    return frm <= md <= to if frm <= to else (md >= frm or md <= to)
def seasonal_active(code, run_day, path="overrides/swep_seasonal.json"):
    """Fixed-season SWEP stated on the council's own page (overrides/swep_seasonal.json, Dean 24 Oct 2026)."""
    try: s = json.load(open(path)).get(code)
    except Exception: return None
    return s if s and in_season(run_day[5:], s["from"], s["to"]) else None
def _fetch(u):
    from discover import fetch_raw
    return fetch_raw(u)
def page_text(html):
    return html_to_visible_text(html)
def run(fetcher=None, run_day=None, threads=8):
    fetcher = fetcher or _fetch; run_day = run_day or datetime.date.today().isoformat()
    srcs = [x for x in (json.load(open(SRC)) if os.path.exists(SRC) else []) if x.get("url")]  # council records without a SWEP page carry url null
    prev_log = json.load(open(LOG)) if os.path.exists(LOG) else {}
    prev_pages = prev_log.get("pages", [])
    prev = {x["url"]: x for x in prev_pages}
    def one(s):
        r = fetcher(s["url"]); h = r.get("html") or r.get("text") or ""
        txt = page_text(h)
        st, q = classify_html(h, run_day) if r.get("http") == 200 else ("unreachable", "")
        p = {"council": s["council"], "url": s["url"], "http": r.get("http"), "status": st, "quote": q,
             "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "_text": txt}
        try:
            import incident_rest_centre_switch_on as irso
            irso.enrich_page(p, txt, run_day)
        except Exception:
            p["rest_centre"] = p.get("rest_centre")
        return p
    with cf.ThreadPoolExecutor(threads) as ex: pages = list(ex.map(one, srcs))
    changes = []
    for p in pages:
        o = prev.get(p["url"])
        if o and o["status"] != p["status"] and "active" in (o["status"], p["status"]) or (not o and p["status"] == "active"):
            changes.append({"council": p["council"], "url": p["url"], "from": (o or {}).get("status", "new"), "to": p["status"], "quote": p["quote"]})
    rc_pages, rc_seconds, rc_prev = _rest_centre_pages(run_day)
    saved = []
    for p in pages:
        q = dict(p)
        q.pop("_text", None)
        saved.append(q)
    out = {"run": run_day, "sources": len(srcs), "active": [p["council"] for p in saved if p["status"] == "active"], "changes": changes, "pages": saved}
    json.dump(out, open(LOG, "w"), indent=1, ensure_ascii=False)
    try:
        import rest_centre_sources as rcsrc
        rcsrc.save_log(rc_pages, run_day, rc_seconds)
    except Exception as e:
        print("::error::rest centre (council-run) log failed: %s: %s" % (type(e).__name__, e), file=sys.stderr)
    alert_error = _switch_on(prev_pages, rc_prev, pages, rc_pages, run_day)
    if alert_error:
        out["alert_error"] = alert_error
    if rc_pages:
        print("rest centre (council-run) scan: %d pages in %.0fs" % (len(rc_pages), rc_seconds or 0))
    return out
def discover(fetcher=None, councils_path="scripts/sweep_sources.json", budget_s=1500):
    """Overnight: scan council sites for SWEP / rough sleeping pages. Adds new URLs to overrides/swep_sources.json."""
    fetcher = fetcher or _fetch
    cs = json.load(open(councils_path))["councils"]
    have = json.load(open(SRC)) if os.path.exists(SRC) else []
    seen = {x["url"] for x in have if x.get("url")}; t0 = time.time()
    def one(c):
        found = []
        for u in [c["site"]] + [u for u in c.get("known_pages", [])[:1]]:
            r = fetcher(u)
            if r.get("http") != 200: continue
            for href, txt in LINK.findall(r.get("html") or ""):
                if LINKWORDS.search(href + " " + txt):
                    full = urllib.parse.urljoin(u, href)
                    if urllib.parse.urlparse(full).netloc.split(":")[0].endswith(urllib.parse.urlparse(c["site"]).netloc.replace("www.", "")):
                        found.append({"council": c["name"], "url": full, "found_on": u})
        return found
    added = []
    with cf.ThreadPoolExecutor(6) as ex:
        for f in ex.map(one, cs):
            for x in f:
                if x["url"] not in seen: seen.add(x["url"]); have.append(x); added.append(x)
            if time.time() - t0 > budget_s: break
    json.dump(have, open(SRC, "w"), indent=1, ensure_ascii=False)
    return {"councils": len(cs), "sources": len(have), "added": len(added)}

FULL_LOG, FULL_MD = "logs/swep_full.json", "reports/swep_daily.md"
def full(fetcher=None, run_day=None, threads=8):
    """Daily full-coverage check (Dean, 23 Oct 2026): every UK council in scripts/sweep_sources.json.
    Re-checks each council's SWEP page, flags new / dead pages and status changes, lists councils with no SWEP page.
    Writes logs/swep_full.json + reports/swep_daily.md. Never contacts anyone; reads public pages only."""
    fetcher = fetcher or _fetch; run_day = run_day or datetime.date.today().isoformat()
    cs = json.load(open("scripts/sweep_sources.json"))["councils"]
    srcs = json.load(open(SRC)) if os.path.exists(SRC) else []
    by = {}
    for x in srcs:
        k = x.get("code") or x.get("council"); by.setdefault(k, []).append(x)
    prev = json.load(open(FULL_LOG)) if os.path.exists(FULL_LOG) else {}
    pp = {c["code"]: c for c in prev.get("councils", [])}
    def one(c):
        recs = by.get(c["code"], []) + [x for x in by.get(c["name"], []) if x not in by.get(c["code"], [])]
        urls = [x["url"] for x in recs if x.get("url")]
        line = next((x for x in recs if x.get("homeless_phone") or x.get("ooh_phone")), {})
        res = {"code": c["code"], "council": c["name"], "nation": c["nation"], "homeless_phone": line.get("homeless_phone"),
               "ooh_phone": line.get("ooh_phone"), "phone_source": line.get("phone_source"), "pages": []}
        for u in urls[:3]:
            r = fetcher(u); h = r.get("html") or r.get("text") or ""
            txt = page_text(h)
            st, q = classify_html(h, run_day) if r.get("http") == 200 else ("unreachable", "")
            pg = {"url": u, "http": r.get("http"), "status": st, "quote": q, "rest_centre": None}
            try:
                import incident_rest_centre_switch_on as irso
                work = dict(pg, council=c["name"], url=u)
                irso.enrich_page(work, txt, run_day)
                pg["rest_centre"] = work.get("rest_centre")
            except Exception:
                pass
            res["pages"].append(pg)
        res["status"] = next((p["status"] for p in res["pages"] if p["status"] == "active"), res["pages"][0]["status"] if res["pages"] else "no SWEP page")
        sz = seasonal_active(c["code"], run_day)
        if sz: res["status"] = "active"; res["pages"].append({"url": sz["url"], "http": None, "status": "active", "quote": "seasonal (council page): " + sz["quote"]})
        o = pp.get(c["code"])
        flags = []
        if not o: flags.append("new council record")
        else:
            if o.get("status") != res["status"]: flags.append("status %s -> %s" % (o.get("status"), res["status"]))
            ou = {p["url"] for p in o.get("pages", [])}
            flags += ["new page " + p["url"] for p in res["pages"] if p["url"] not in ou]
        flags += ["dead page %s (HTTP %s)" % (p["url"], p["http"]) for p in res["pages"] if p["status"] == "unreachable"]
        res["flags"] = flags
        return res
    with cf.ThreadPoolExecutor(threads) as ex: out = list(ex.map(one, cs))
    cov = {"councils": len(out), "with_swep_page": sum(1 for r in out if r["pages"]), "with_line": sum(1 for r in out if r["homeless_phone"] or r["ooh_phone"]),
           "active": [r["council"] for r in out if r["status"] == "active"], "flagged": sum(1 for r in out if r["flags"])}
    prev_full_pages = []
    for c in prev.get("councils", []):
        for p in c.get("pages", []):
            prev_full_pages.append(dict(p, council=c.get("council"), url=p.get("url")))
    new_full_pages = []
    for c in out:
        for p in c.get("pages", []):
            new_full_pages.append(dict(p, council=c.get("council"), url=p.get("url")))
    json.dump({"run": run_day, "coverage": cov, "councils": out}, open(FULL_LOG, "w"), indent=1, ensure_ascii=False)
    rc_pages, rc_seconds, rc_prev = _rest_centre_pages(run_day)
    try:
        import rest_centre_sources as rcsrc
        rcsrc.save_log(rc_pages, run_day, rc_seconds)
    except Exception as e:
        print("::error::rest centre (council-run) log failed: %s: %s" % (type(e).__name__, e), file=sys.stderr)
    alert_error = _switch_on(prev_full_pages, rc_prev, new_full_pages, rc_pages, run_day)
    if alert_error:
        cov["alert_error"] = alert_error
    if rc_pages:
        print("rest centre (council-run) scan: %d pages in %.0fs" % (len(rc_pages), rc_seconds or 0))
    os.makedirs("reports", exist_ok=True)
    with open(FULL_MD, "w") as f:
        f.write("# SWEP daily full check (%s)\n\n%d councils: %d with a SWEP page, %d with a homeless line, %d active, %d flagged.\n\n" % (run_day, cov["councils"], cov["with_swep_page"], cov["with_line"], len(cov["active"]), cov["flagged"]))
        f.write("## Active now\n\n" + ("".join("- %s\n" % a for a in cov["active"]) or "None.\n") + "\n## Changes and flags\n\n")
        f.write("".join("- %s: %s\n" % (r["council"], "; ".join(r["flags"])) for r in out if r["flags"]) or "None.\n")
        f.write("\n## No SWEP page found\n\n" + "".join("- %s (%s)\n" % (r["council"], r["nation"]) for r in out if not r["pages"]))
    return cov
def _rest_centre_pages(run_day):
    try:
        import rest_centre_sources as rcsrc
        prev = rcsrc.load_log_pages()
        pages, seconds = rcsrc.fetch_pages(run_day=run_day)
        return pages, seconds, prev
    except Exception as e:
        print("::error::rest centre (council-run) page check failed: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return [], 0, []


def _switch_on(prev_swep, prev_rc, new_swep, new_rc, run_day):
    try:
        import incident_rest_centre_switch_on as irso
        snap = irso.load_snapshot(os.getcwd())
        prev = snap or (list(prev_swep or []) + list(prev_rc or []))
        result = irso.apply(prev, list(new_swep or []) + list(new_rc or []), run_day=run_day, root=os.getcwd())
        return result.get("error")
    except Exception as e:
        msg = "%s: %s" % (type(e).__name__, e)
        print("::error::rest centre switch-on alert or issue open/close failed: %s" % msg, file=sys.stderr)
        return msg


def finish(result):
    if isinstance(result, dict) and result.get("alert_error"):
        print("::error::rest centre switch-on alert or issue open/close failed: %s" % result["alert_error"], file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if sys.argv[1:] == ["discover"]: print(discover())
    elif sys.argv[1:] == ["full"]:
        r = full(); print(json.dumps({k: v for k, v in r.items() if k != "alert_error"})); finish(r)
    else:
        r = run(); print(r["sources"], "SWEP pages;", len(r["active"]), "active;", len(r["changes"]), "changes"); finish(r)
