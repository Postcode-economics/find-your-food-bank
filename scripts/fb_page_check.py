"""Daily re-check of every verified Facebook page used for the 'Message on Facebook' button (Dean, 23 Oct 23:36).
Baseline: overrides/facebook_pages.json (53 pages hand-verified 23 Oct: page name + town + a second source).
For each page: fetch with Facebook's link-preview agent, read og:title, compare with the baseline page_title.
  ok        - title still matches
  changed   - page loads but the title no longer matches (renamed / taken over / different page)
  dead      - 404/410, or Facebook's 'content isn't available' page
  unreachable - network error or rate-limited (429/5xx); not a finding, re-tried next run
Nothing is ever removed: findings go to logs/fb_page_check.json and reports/fb_pages_flagged.md for Dean."""
import json, os, re, sys, html, time, datetime, urllib.request
UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
def norm(s): return re.sub(r"[^a-z0-9]", "", html.unescape(s or "").lower())
def og_title(h):
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', h or "") or re.search(r"<title>([^<]*)</title>", h or "")
    return html.unescape(m.group(1)).strip() if m else ""
def fetch(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20)
        return r.status, r.read(600_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e: return e.code, ""
    except Exception: return 0, ""
def classify(base_title, code, h):
    if code in (404, 410): return "dead", ""
    if code == 0 or code == 429 or code >= 500: return "unreachable", ""
    t = og_title(h)
    if not t or re.search(r"content isn.t available|page isn.t available|log in or sign up", t + " " + (h or "")[:3000], re.I) and not norm(base_title) in norm(t):
        return ("dead" if re.search(r"isn.t available", h or "", re.I) else "unreachable"), t
    return ("ok" if norm(base_title) and (norm(base_title) in norm(t) or norm(t) in norm(base_title)) else "changed"), t
def run(pages, fetcher=fetch, delay=1.5):
    out = {}
    for k, v in pages.items():
        if k.startswith("_"): continue
        code, h = fetcher(v["url"]); st, t = classify(v.get("page_title", ""), code, h)
        out[k] = {"url": v["url"], "baseline_title": v.get("page_title"), "title_now": t, "http": code, "status": st}
        time.sleep(delay)
    return out
def report(res, run_day):
    bad = {k: r for k, r in res.items() if r["status"] in ("changed", "dead")}
    L = ["# Facebook pages flagged for Dean", "", f"Run {run_day}. {len(res)} pages checked; {len(bad)} flagged. Nothing was removed from the map.", ""]
    L += [f"- `{k}` **{r['status']}**: {r['url']} (baseline '{r['baseline_title']}', now '{r['title_now']}', HTTP {r['http']})" for k, r in sorted(bad.items())] or ["Nothing flagged."]
    return "\n".join(L) + "\n"
if __name__ == "__main__":
    pages = json.load(open("overrides/facebook_pages.json")); day = datetime.date.today().isoformat()
    res = run(pages); os.makedirs("logs", exist_ok=True); os.makedirs("reports", exist_ok=True)
    json.dump({"run": day, "pages": res}, open("logs/fb_page_check.json", "w"), indent=1, ensure_ascii=False)
    open("reports/fb_pages_flagged.md", "w").write(report(res, day))
    c = {}; [c.__setitem__(r["status"], c.get(r["status"], 0) + 1) for r in res.values()]; print(c)
