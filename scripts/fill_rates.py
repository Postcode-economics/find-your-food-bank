"""Silent-breakage detection (Dean, 23 Oct 23:42). Each run, BEFORE the refresh guard restores dropped values, record the
fill rate per source for opening times, phones and Facebook pages, compare with a rolling baseline of the last 7 runs
(reports/fill_rates.json), and flag a sharp drop as a likely site/API change:
  drop of more than 30 points, or 0% now when the baseline was above 20%.
A flagged source is NOT read as 'these places have no data': the refresh guard keeps their existing values, and an alert
goes at the top of reports/daily_review.md plus a GitHub issue (scripts/alert.py, key 'fill-<source>').
Sources: food banks split into Trussell Trust (*.foodbank.org.uk), IFAN, Give Food (independent), and each own-site
family (one host with 5+ centres); shelters and warm spaces split by their 'source' field.
Usage: fill_rates.py [kind ...]  (kinds: foodbanks shelters warmspaces; default all). Exit code is always 0."""
import json, os, re, sys, datetime, collections, urllib.parse
ROOT = os.path.join(os.path.dirname(__file__), "..")
BASE = os.path.join(ROOT, "reports", "fill_rates.json"); REVIEW = os.path.join(ROOT, "reports", "daily_review.md")
KEEP, DROP_PTS, ZERO_FROM, MIN_N = 7, 30.0, 20.0, 5
NICE = {"times": "opening times", "phone": "phone numbers", "fb_page": "Facebook pages", "times_confirmed": "own-site confirmed opening times"}
def load_items(path, var=None):
    s = open(path).read(); d = json.loads(s[s.index("{"): s.rindex("}") + 1]); return d.get("items", [])
def fb_source(i):
    w = (i.get("website") or "").lower(); h = urllib.parse.urlparse(w).netloc.removeprefix("www.")
    if h.endswith(".foodbank.org.uk"): return "Trussell Trust pages"
    if i.get("directory") == "IFAN" or i["id"].startswith("ifan-"): return "IFAN"
    return "Give Food (independent)"
def has_times(v):
    if isinstance(v, dict): return bool(v.get("status") in ("TIMES_FOUND", "TIMES_TEXT_ONLY") or v.get("structured") or v.get("raw"))
    return bool(v)
def rates(kind, items):
    """-> {source: {metric: (pct, n)}}"""
    g = collections.defaultdict(list)
    for i in items:
        if kind == "foodbanks":
            g[fb_source(i)].append(i)
            h = urllib.parse.urlparse((i.get("website") or "").lower()).netloc.removeprefix("www.")
            if h and "facebook" not in h: g["own site " + h].append(i)
        else: g[f"{kind}: {i.get('source') or 'unknown'}"].append(i)
    out = {}
    for src, its in g.items():
        if len(its) < MIN_N: continue
        m = {}
        tf = "opening_times" if kind == "foodbanks" else "hours"
        m["times"] = sum(has_times(i.get(tf)) for i in its)
        m["phone"] = sum(bool(i.get("phone") or i.get("tel")) for i in its)
        if kind == "foodbanks":
            m["fb_page"] = sum(bool(i.get("fb_page")) for i in its)
            m["times_confirmed"] = sum(i.get("times_status") in ("confirmed", "updated", "confirmed_by_hand") for i in its)
        out[src] = {k: [round(100.0 * v / len(its), 1), len(its)] for k, v in m.items()}
    return out
def check(now, history):
    """now: {source: {metric: [pct, n]}}; history: list of past runs' same shape. -> list of alert dicts."""
    alerts = []
    for src, ms in now.items():
        for met, (pct, n) in ms.items():
            past = [h[src][met][0] for h in history[-KEEP:] if src in h and met in h[src]]
            if len(past) < 2: continue   # need a baseline first
            base = sum(past) / len(past)
            if (base - pct > DROP_PTS) or (pct == 0 and base > ZERO_FROM):
                alerts.append({"source": src, "metric": met, "now": pct, "baseline": round(base, 1), "n": n,
                               "text": f"{src} returned {pct:g}% {NICE.get(met, met)} today, down from {base:.0f}%. Possible site change."})
    return alerts
def prepend_review(alerts, path=REVIEW):
    old = open(path).read() if os.path.exists(path) else ""
    old = re.sub(r"(?s)^<!-- fill-rate alerts -->.*?<!-- /fill-rate alerts -->\n*", "", old)
    if not alerts: open(path, "w").write(old); return
    blk = ["<!-- fill-rate alerts -->", "## ⚠ Likely breakage (fill-rate alert)", ""]
    blk += [f"- {a['text']} ({a['n']} places; existing values kept by the refresh guard, not treated as missing.)" for a in alerts]
    blk += ["<!-- /fill-rate alerts -->", "", ""]
    open(path, "w").write("\n".join(blk) + old)
def main(kinds, run_id=None, issue=True):
    files = {"foodbanks": "data.full.js", "shelters": "shelters.js", "warmspaces": "warmspaces.js"}
    now = {}
    for k in kinds:
        p = os.path.join(ROOT, files[k])
        if os.path.exists(p): now.update(rates(k, load_items(p)))
    st = json.load(open(BASE)) if os.path.exists(BASE) else {"runs": []}
    hist = [r["rates"] for r in st["runs"]]
    alerts = check(now, hist)
    st["runs"] = (st["runs"] + [{"run": run_id or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "rates": now, "alerts": [a["text"] for a in alerts]}])[-KEEP:]
    os.makedirs(os.path.dirname(BASE), exist_ok=True); json.dump(st, open(BASE, "w"), indent=1, ensure_ascii=False)
    prepend_review(alerts)
    if issue:
        import subprocess
        for a in alerts:
            key = "fill-" + re.sub(r"[^a-z0-9]+", "-", a["source"].lower()).strip("-")[:40]
            subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "alert.py"), "open", key, "Likely breakage: " + a["source"], a["text"] + " Existing values were kept (refresh guard). Check the source page/API."])
    print(len(now), "sources measured;", len(alerts), "alerts"); [print(" ", a["text"]) for a in alerts]
    return alerts
if __name__ == "__main__":
    try: main([a for a in sys.argv[1:]] or ["foodbanks", "shelters", "warmspaces"])
    except Exception as e: print("::warning::fill_rates failed:", e)
