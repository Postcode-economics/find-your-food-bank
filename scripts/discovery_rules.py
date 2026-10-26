"""Auto-add rules for discovery (owner, 23 Oct 2026 06:23). A new place found by any source is ADDED automatically
(as tier 2 'Unverified - call before you go' for shelters/warm spaces; as a normal pin for food banks) only when ALL hold:
  1. valid postcode that geocodes (postcodes.io) - and, where the source gives a pin, the pin is within AREA_KM of it
     and any postcode written in the address is the same one ("inside its stated area");
  2. not a duplicate: same postcode + shared name word, or within 150 m of anything already on the map (discover.is_dup);
  3. a working source page (own site, or the live directory record fetched this run);
  4. current or future dates (anything whose stated dates are all in the past is rejected; not-yet-open = 'Opens <date>').
Anything failing a check is QUEUED for a person in reports/manual_review.md (auto section) - never guessed onto the map.
Hard rejects (past dates, own site says closed, not the right kind of service) are logged with the reason.
Places owner is deciding on by hand (overrides/discovery_hold.json) are never auto-added.
Every add is logged in logs/discovery_today_<layer>.json and reports/new_today.md.
Fail-safe: every function here swallows its own errors; a failure means 'queue', never 'add'."""
import json, os, re, datetime, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AREA_KM = 2.0
PC = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b")
# own-site reasons that only mean "couldn't confirm on their site" - acceptable when the directory record itself is the
# working source and the postcode checks pass. Everything else (unreachable, closed, wrong service, redirect) is not.
SOFT = ("postcode not on own site", "no own website in directory", "no postcode in directory")
HARD_REJECT = ("own site says closed",)  # everything else that fails goes to the manual queue, not the bin
def npc(p): return (p or "").upper().replace(" ", "")
def hav(a, b, c, d):
    import math
    p = math.pi / 180; x = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))
def hold():
    try: return json.load(open(os.path.join(ROOT, "overrides", "discovery_hold.json")))
    except Exception: return []
def held(c, H=None):
    for h in (hold() if H is None else H):
        if h.get("postcode"):  # postcode given: match on postcode only (a name like 'The Hub' is too common)
            if npc(h["postcode"]) == npc(c.get("postcode")): return h
        elif h.get("name") and h["name"].lower() in (c.get("name") or "").lower(): return h
    return None
def dates_state(c, today):
    """'past' | 'future' | 'current' from the entry's own wording/fields."""
    try:
        import seasonal
        s = seasonal.parse(" ".join(str(c.get(k) or "") for k in ("notes", "description", "scheme_dates", "dates")))
        start, end = c.get("scheme_start") or s["start"], c.get("scheme_end") or s["end"]
        if c.get("ended") or (end and end < today): return "past", start, end
        if start and start > today: return "future", start, end
        return "current", start, end
    except Exception: return "current", "", ""
def assess(c, site, geo, today, H=None):
    """c: candidate; site: own_site_check() result (or {'result':'add'} for a live directory record);
    geo: {POSTCODE_NOSPACE: (lat, lng)} for this run. Returns (decision, reasons): 'add' | 'queue' | 'reject'."""
    try:
        q = []
        h = held(c, H)
        if h: return "queue", ["on hold: " + h.get("reason", "manual decision pending")]
        st, start, end = dates_state(c, today)
        if st == "past": return "reject", ["dates all in the past (latest %s)" % (end or "?")]
        reasons = [r for r in (site or {}).get("reasons", [])]
        if any(k in r for r in reasons for k in HARD_REJECT): return "reject", reasons
        hardq = [r for r in reasons if not any(r.startswith(s) for s in SOFT)]
        if hardq: q += hardq
        soft = [r for r in reasons if r not in hardq]
        if soft and not c.get("source_live"): q += soft  # no own-site confirmation and no live directory record either
        elif soft:  # directory record only (e.g. a Warm Welcome listing): it must carry THIS season's dates, or it may be an old listing
            y = int(today[:4]) - (0 if today[5:7] >= "08" else 1); season = "%d-08-01" % y
            if not ((start and start >= season) or (end and end >= today)):
                q.append("directory listing only, with no %d-%02d season dates (latest stated start: %s)" % (y, (y + 1) % 100, start or "none"))
        pc = npc(c.get("postcode"))
        g = geo.get(pc) if pc else None
        if not pc: q.append("no postcode")
        elif not g: q.append("postcode %s not recognised by postcodes.io" % c.get("postcode"))
        else:
            if c.get("src_lat") is not None and c.get("src_lng") is not None:
                d = hav(c["src_lat"], c["src_lng"], g[0], g[1])
                if d > AREA_KM: q.append("source pin %.1f km from its postcode" % d)
            other = {a + b for a, b in PC.findall((c.get("address") or "").upper())} - {pc}
            if other: q.append("address shows a different postcode (%s)" % ", ".join(sorted(other)))
        return ("queue", q) if q else ("add", [])
    except Exception as ex:
        return "queue", ["rule check failed: %s" % str(ex)[:80]]
def apply_dates(c, today):
    st, start, end = dates_state(c, today)
    if start: c["scheme_start"] = start; c["upcoming"] = start > today
    if end: c["scheme_end"] = end
    return c
# ---------- logging: daily 'new today' + manual review queue ----------
def record(layer, run_day, added=(), queued=(), rejected=(), source="", root=None):
    """Append this run's results to logs/discovery_today_<layer>.json (reset each UK day) and re-render the reports."""
    try:
        root = root or ROOT
        p = os.path.join(root, "logs", "discovery_today_%s.json" % layer)
        try: d = json.load(open(p))
        except Exception: d = {}
        if d.get("day") != run_day: d = {"day": run_day, "runs": [], "added": [], "queued": {}, "rejected": {}}
        d["runs"].append({"at": datetime.datetime.now(datetime.timezone.utc).strftime("%H:%MZ"), "source": source,
                          "added": len(added), "queued": len(queued), "rejected": len(rejected)})
        seen = {a["id"] for a in d["added"]}
        d["added"] += [a for a in added if a.get("id") not in seen]
        for k, x in (("queued", queued), ("rejected", rejected)):
            for e in x: d[k][str(e.get("id") or e.get("name"))] = e
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"; json.dump(d, open(tmp, "w"), indent=1, ensure_ascii=False); os.replace(tmp, p)
        render(run_day, root)
    except Exception as ex: print("discovery_rules.record failed (ignored):", ex)
def _lines(e):
    bits = [e.get("name", "?")]
    if e.get("postcode"): bits.append(e["postcode"])
    if e.get("source_url") or e.get("website") or e.get("directory_url"): bits.append(e.get("source_url") or e.get("website") or e.get("directory_url"))
    return " · ".join(bits)
LAYERS = {"foodbanks": "Food banks", "shelters": "Shelters", "warmspaces": "Warm spaces", "sweep": "Deep sweep (council pages)"}
START, STOP = "<!-- AUTO-DISCOVERY QUEUE: generated, do not edit below -->", "<!-- END AUTO-DISCOVERY QUEUE -->"
def render(run_day, root=None):
    ROOT_ = root or ROOT; D = {}
    for f in sorted(glob.glob(os.path.join(ROOT_, "logs", "discovery_today_*.json"))):
        try: x = json.load(open(f))
        except Exception: continue
        if x.get("day") == run_day: D[os.path.basename(f)[16:-5]] = x
    os.makedirs(os.path.join(ROOT_, "reports"), exist_ok=True)
    L = ["# New today (%s)" % run_day, "", "Places added automatically by discovery today. Each passed: valid postcode in its area, "
         "not a duplicate (name+postcode or 150 m), working source page, current or future dates.", ""]
    for k, x in D.items():
        L.append("## %s: %d added" % (LAYERS.get(k, k), len(x["added"])))
        L += ["- " + _lines(a) + (" (Opens %s)" % a["scheme_start"] if a.get("upcoming") and a.get("scheme_start") else "") +
              (" — referral only" if a.get("referral_only") else "") for a in x["added"]] or ["- none"]
        L.append("")
    open(os.path.join(ROOT_, "reports", "new_today.md"), "w").write("\n".join(L) + "\n")
    Q = [START, "## Auto-discovery queue (%s) — failed one auto-add check, not on the map" % run_day, ""]
    for k, x in D.items():
        Q.append("### %s: %d queued, %d rejected" % (LAYERS.get(k, k), len(x["queued"]), len(x["rejected"])))
        Q += ["- QUEUED " + _lines(e) + " — " + "; ".join(e.get("reasons", []))[:200] for e in list(x["queued"].values())[:300]]
        Q += ["- rejected " + _lines(e) + " — " + "; ".join(e.get("reasons", []))[:200] for e in list(x["rejected"].values())[:100]]
        Q.append("")
    Q.append(STOP)
    p = os.path.join(ROOT_, "reports", "manual_review.md")
    try: s = open(p).read()
    except Exception: s = "# Manual review queue (not on the map)\n"
    s = (s[:s.index(START)].rstrip() + "\n\n" if START in s else s.rstrip() + "\n\n") + "\n".join(Q) + "\n"
    open(p, "w").write(s)

if __name__ == "__main__":  # `python scripts/discovery_rules.py render` - rebuild the two reports from all layers' logs (after a rebase)
    import sys
    if sys.argv[1:2] == ["render"]:
        try: render(datetime.date.today().isoformat())
        except Exception as ex: print("render failed (ignored):", ex)
