"""Point 8 (24 Oct 2026, approved by Dean): source-quality score.
Score per source (0-100) = average of its opening-times and phone fill rates in the latest run of reports/fill_rates.json
(Facebook-page fill is not counted: most good places have no Facebook page). Scores come only from data already recorded.
A source is flagged when its score falls more than DROP points below the median of its previous (up to 7) runs.
Writes reports/source_scores.md. scores()/drops() are used by digest.py for alert (3). Never fails the job."""
import json, os, statistics
ROOT = os.path.join(os.path.dirname(__file__), "..")
FR = os.path.join(ROOT, "reports", "fill_rates.json"); MD = os.path.join(ROOT, "reports", "source_scores.md")
DROP, KEEP = 15.0, 7
def score(ms):
    v = [ms[k][0] for k in ("times", "phone") if k in ms]
    return round(sum(v) / len(v), 1) if v else None
def scores(run): return {s: sc for s, ms in run.get("rates", {}).items() if (sc := score(ms)) is not None}
def drops(runs):
    if not runs: return [], {}
    now = scores(runs[-1]); past = [scores(r) for r in runs[:-1][-KEEP:]]; out = []
    for s, sc in now.items():
        prev = [p[s] for p in past if s in p]
        if len(prev) >= 2 and statistics.median(prev) - sc > DROP: out.append((s, sc, statistics.median(prev)))
    return out, now
def main():
    try: runs = json.load(open(FR)).get("runs", [])
    except Exception: runs = []
    dr, now = drops(runs)
    L = ["# Source quality scores (point 8)", "", "Score = average of opening-times and phone fill rates (0-100). Flagged if it drops more than %g points below its usual level." % DROP, ""]
    L += ["## Dropped", ""] + (["- **%s**: %g, usually %g" % d for d in dr] or ["- none"]) + ["", "## All sources (lowest first)", ""]
    L += ["- %s: %g" % (s, v) for s, v in sorted(now.items(), key=lambda x: x[1])]
    open(MD, "w", encoding="utf-8").write("\n".join(L) + "\n"); return dr
if __name__ == "__main__":
    try: print("source score drops:", main())
    except Exception as e: print("source score failed (not fatal):", e)
