"""Point 9 (24 Oct 2026): alert triggers + morning digest.
Immediate alerts (GitHub issue via alert.py, the existing mechanism):
  (1) a food bank closed (real closure in logs/entry_history.json this run)
  (2) likely duplicates spike: more than BASE+5 vs the median of the last 7 runs (logs/duplicates.json)
  (4) weather/flood: Met Office amber/red or severe flood warning (point 27, reports/weather.json)
  (3) a source's quality score dropped (point 8, scripts/source_score.py: more than 15 points below its usual level)
  Sources disappearing are already alerted by fill_rates.py (0% / sharp drop).
Everything else goes in reports/morning_digest.md. Never fails the job."""
import datetime, json, os, statistics, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__)); import source_score, learning
ROOT = os.path.join(os.path.dirname(__file__), "..")
P = lambda *a: os.path.join(ROOT, *a)
ST = P("logs", "digest_state.json"); MD = P("reports", "morning_digest.md")
def rj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def triggers(state, history, dups, since, weather=None):
    al = []
    closed = [c for v in history.values() for c in v if c.get("label", "").startswith("real closure") and c.get("when", "") >= since]
    if closed: al.append(("closure", "Food bank closed", "Removed because its own site says it closed: " + ", ".join(sorted({c.get('name') or c['id'] for c in closed}))))
    likely = sum(1 for d in dups if d.get("kind") == "likely duplicate"); prev = state.get("dups", [])[-7:]
    if prev and likely > statistics.median(prev) + 5: al.append(("dup-spike", "Duplicates spiked", "Likely duplicates %d vs usual %g - see reports/duplicates.md" % (likely, statistics.median(prev))))
    try: sd = source_score.drops(rj(P("reports", "fill_rates.json"), {}).get("runs", []))[0]
    except Exception: sd = []
    if sd: al.append(("source-score", "Source quality dropped", "; ".join("%s now %g (usually %g)" % d for d in sd) + " - see reports/source_scores.md"))
    wx = weather or []
    ur = [w for w in wx if w.get("level") in ("amber", "red")]
    if ur: al.append(("weather", "Amber/red weather or severe flood warning", "; ".join("%s (shelters/warm spaces: %s; SWEP: %s)" % (w["title"], ", ".join(w.get("places", [])[:10]) or "none matched", ", ".join(w.get("swep", [])) or "none") for w in ur) + " - see reports/weather.md" + ("".join(sorted({" " + w["credit"] + "." for w in ur if w.get("credit")})))))
    return al, likely, closed
def main(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    state = rj(ST, {}); since = state.get("last_run", (now - datetime.timedelta(days=1)).isoformat(timespec="seconds"))
    al, likely, closed = triggers(state, rj(P("logs", "entry_history.json"), {}), rj(P("logs", "duplicates.json"), []), since, rj(P("reports", "weather.json"), {}).get("warnings", []))
    errs = rj(P("reports", "source_errors.json"), {}).get("errors", [])
    hist = rj(P("logs", "entry_history.json"), {}); recent = [c for v in hist.values() for c in v if c.get("when", "") >= since]
    sw = rj(P("logs", "swep_tracker.json"), {}).get("days", {}); swl = sw[max(sw)]["still_to_check"] if sw else None
    L = ["# Morning digest - %s" % now.date(), "", "## Alerts this run", ""] + (["- **%s**: %s" % (t, b) for _, t, b in al] or ["- none"]) + ["",
         "## Everything else", "", "- Changes since last run: %d (%d new, %d removed, %d field updates)" % (len(recent), sum(c["change"] == "added" for c in recent), sum(c["change"] == "removed" for c in recent), sum(c["change"] not in ("added", "removed") for c in recent)),
         "- Likely duplicates on the map: %d (reports/duplicates.md)" % likely,
         "- Weather/flood warnings: %d (reports/weather.md)" % len(rj(P("reports", "weather.json"), {}).get("warnings", [])),
         "- Source quality scores: reports/source_scores.md",
         "- Source errors this run: %d (reports/source_errors.json)" % len(errs),
         "- SWEP councils still to check: %s (reports/swep_tracker.md)" % ("n/a" if swl is None else swl),
         "- Daily review list: reports/daily_review.md", ""]
    try: L += learning.digest_lines(learning.load(), now.date().isoformat())  # owner 25 Oct 08:01
    except Exception as e: L += ['## What the system learned', '', '- unavailable: %r' % e, '']
    try:
        import learning_signals; L += learning_signals.digest_lines(rj(P('reports', 'learning_signals.json'), {})) if os.path.exists(P('reports', 'learning_signals.json')) else []
    except Exception as e: L += ['- learning signals unavailable: %r' % e, '']
    open(MD, "w", encoding="utf-8").write("\n".join(L))
    if os.environ.get("GITHUB_ACTIONS"):
        for k, t, b in al: subprocess.run([sys.executable, P("scripts", "alert.py"), "open", k, t, b])
    state["dups"] = (state.get("dups", []) + [likely])[-30:]; state["last_run"] = now.isoformat(timespec="seconds")
    json.dump(state, open(ST, "w"), indent=1); return al
if __name__ == "__main__":
    try: print("digest alerts:", [a[0] for a in main()])
    except Exception as e: print("digest failed (not fatal):", e)
