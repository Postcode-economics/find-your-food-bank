"""Safety rails for intelligent mode (Dean, 29 Oct 2026).

The switch is overrides/auto_apply_rules.json key intelligent_mode. It stays false until Dean
turns it on. While it is false, auto-apply paths do not consult these rails, so published
listings and the existing reports stay as they are. A refresh still writes
reports/intelligent_mode.json so the 8am digest can see a thin read.

When the switch is on, a thin read or a blast above the cap applies nothing from that step.
The rest of the refresh still publishes. Stale queue rows (the held value already matches the
live listing) are cleared and never re-applied. Phones and council lines are never auto-changed.
"""
import datetime, json, os, re, time
import phone_lock

LOCKED_FIELDS = phone_lock.FIELDS
RUN_CAP = 40
LAYER_CAP = 40
MIN_SOURCE_SHARE = 0.80
MAX_RENDER_ERROR_SHARE = 0.25
MIN_RENDER_ATTEMPTS = 8
ALERT = "INTELLIGENT MODE ALERT"
SUMMARY = os.path.join("reports", "intelligent_mode.json")
_DELAYS = (0, 0.4, 1.2)
_OUTAGE = re.compile(
    r"dns|name or service not known|temporary failure in name resolution|timed out|connection reset|errno",
    re.I)
_ROW = re.compile(r"^- \*\*.*?\*\* \(`([^`]+)`,\s*([^)]*)\):\s*own site now\s+(.*)$")
_LAYERS = {"fb": "foodbanks", "ws": "warmspaces", "sh": "shelters", "sweep": "sweep"}
_stats, _mem, _stale_logged = {}, {}, set()
_lock = __import__("threading").Lock()


def layer_name(kind):
    return _LAYERS.get(kind, kind or "")


def enabled(rules=None):
    if rules is None:
        try:
            import auto_rules
            rules = auto_rules.load()
        except Exception:
            return False
    return bool((rules or {}).get("intelligent_mode"))


def reset():
    """Drop in-process counters. Production processes start empty; tests call this."""
    with _lock:
        _stats.clear()
        _mem.clear()
        _stale_logged.clear()


def note(layer, **kw):
    """Record this run's read. Totals are last-write-wins. Missing keys are not a thin read."""
    if not layer:
        return
    with _lock:
        _stats.setdefault(layer, {}).update(kw)


def note_render(ok, layer="foodbanks"):
    with _lock:
        slot = _stats.setdefault(layer, {})
        slot["render_attempts"] = int(slot.get("render_attempts") or 0) + 1
        if not ok:
            slot["render_errors"] = int(slot.get("render_errors") or 0) + 1


def summary_path(root):
    return os.path.join(root or ".", SUMMARY)


def load_summary(root=None):
    try:
        return json.load(open(summary_path(root), encoding="utf-8"))
    except Exception:
        return {}


def _today():
    return datetime.date.today().isoformat()


def merged(layer, root=None):
    """In-process notes, filled in with today's summary for keys this process has not noted."""
    with _lock:
        stats = dict(_stats.get(layer) or {})
    data = load_summary(root) if root else {}
    if data.get("run") != _today():
        return stats
    saved = ((data.get("layers") or {}).get(layer) or {}).get("coverage") or {}
    for k, v in saved.items():
        stats.setdefault(k, v)
    return stats


def coverage_reasons(stats):
    """Why this run read too little. Empty when the figures are missing or healthy."""
    if not stats:
        return []
    why = []
    pages, opened = stats.get("source_pages"), stats.get("source_opened")
    if isinstance(pages, int) and pages > 0 and isinstance(opened, int) and opened / pages < MIN_SOURCE_SHARE:
        why.append("opened %d of %d source pages (%.0f%% < %.0f%%)" % (opened, pages, 100.0 * opened / pages, 100 * MIN_SOURCE_SHARE))
    sites, sopen = stats.get("sites"), stats.get("sites_opened")
    if isinstance(sites, int) and sites > 0 and isinstance(sopen, int) and sopen / sites < MIN_SOURCE_SHARE:
        why.append("opened %d of %d own sites (%.0f%% < %.0f%%)" % (sopen, sites, 100.0 * sopen / sites, 100 * MIN_SOURCE_SHARE))
    skipped = stats.get("budget_skipped")
    if isinstance(skipped, int) and skipped > 0:
        why.append("full_check budget exhausted (%d sites not checked)" % skipped)
    due, hop = stats.get("hours_review_due"), stats.get("hours_review_opened")
    if isinstance(due, int) and due > 0 and hop == 0:
        why.append("hours review got no time (%d listings not opened)" % due)
    att, err = int(stats.get("render_attempts") or 0), int(stats.get("render_errors") or 0)
    if att >= MIN_RENDER_ATTEMPTS and err / att > MAX_RENDER_ERROR_SHARE:
        why.append("render errors %d of %d (%.0f%% > %.0f%%)" % (err, att, 100.0 * err / att, 100 * MAX_RENDER_ERROR_SHARE))
    return why


def already_published(live, new):
    """True when the held or newly read value is already what the card shows."""
    import discover
    if discover.hours_match(live, new):
        return True
    if isinstance(live, dict) and isinstance(new, dict) and "status" not in live and "status" not in new and live and new:
        def n(h):
            return {str(k)[:3].lower(): re.sub(r"\s+", "", str(v)) for k, v in h.items() if v}
        return n(live) == n(new)
    if isinstance(live, str) and isinstance(new, str):
        a, b = re.sub(r"\s+", " ", live.strip()), re.sub(r"\s+", " ", new.strip())
        return bool(a) and a == b
    return False


def matching_ids(text, live, tag):
    """Pending rows in one section whose 'own site now' text already matches the live value."""
    import discover
    out = []
    for block in discover._pending_bullets(text or "", tag):
        m = _ROW.match(block.splitlines()[0].strip())
        if not m:
            continue
        iid, published = m.group(1), (live or {}).get(m.group(1))
        if published is None:
            continue
        got = discover.extract_times(m.group(3).strip(), None)
        if got and already_published(published, got):
            out.append(iid)
    return out


def log_stale(key):
    with _lock:
        if key in _stale_logged:
            return
        _stale_logged.add(key)
    print("intelligent mode: stale queue cleared %s (held value already equals the live published value)" % key, flush=True)


def clear_pending_stale(root, live_by_kind):
    """Remove pending times rows that already match the live listing. Caller runs this only when the switch is on."""
    path = os.path.join(root or ".", "reports", "pending_dean.md")
    if not os.path.exists(path):
        return {}
    import discover
    text = open(path, encoding="utf-8").read()
    cleared = {}
    for kind, live in (live_by_kind or {}).items():
        ids = matching_ids(text, live, "times crosscheck " + kind)
        if not ids:
            continue
        for iid in ids:
            log_stale("%s:%s" % (kind, iid))
        discover._write_times_pending(root, kind, [], ids, "merge")
        cleared[kind] = ids
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    return cleared


def applied_today(root, layer=None):
    data = load_summary(root) if root else {}
    if data.get("run") != _today():
        data = {}
    layers = data.get("layers") or {}
    with _lock:
        if layer:
            return int((layers.get(layer) or {}).get("applied") or 0) + int(_mem.get(layer) or 0)
        return sum(int((s or {}).get("applied") or 0) for s in layers.values()) + sum(_mem.values())


def record_applied(layer, n):
    if layer and n:
        with _lock:
            _mem[layer] = int(_mem.get(layer) or 0) + int(n)


def blast_reason(n, layer, root=None):
    """Above the cap, the whole batch waits. n is how many this step is about to apply."""
    n = int(n or 0)
    if n <= 0:
        return ""
    run_n = applied_today(root) + n
    layer_n = applied_today(root, layer) + n
    if run_n > RUN_CAP:
        return "blast limit: %d auto-applies this run would pass %d; everything held for review" % (run_n, RUN_CAP)
    if layer_n > LAYER_CAP:
        return "blast limit: %d auto-applies in %s would pass %d; everything held for review" % (layer_n, layer or "?", LAYER_CAP)
    return ""


def batch_block(rules, n, layer, root=None):
    """Reason to hold every auto-apply in this step, or '' when the step may apply."""
    if not enabled(rules):
        return ""
    cov = coverage_reasons(merged(layer, root))
    if cov:
        return "coverage gate: " + "; ".join(cov)
    return blast_reason(n, layer, root)


def strict_reasons(proposal):
    """Audit checklist for one auto-apply. Empty means every rail on this proposal holds.
    proposal: runs [{sig, source_url, run_at}], own (bool), conflict (bool),
    known_hours (bool), new_empty (bool), undo (str), field (str)."""
    p = proposal or {}
    why = []
    runs = list(p.get("runs") or [])
    sigs = [r.get("sig") for r in runs]
    urls = [r.get("source_url") for r in runs]
    ats = [r.get("run_at") for r in runs]
    if len(runs) < 2 or not sigs or not sigs[0] or len(set(map(str, sigs))) != 1 or len(set(urls)) != 1 or len(set(ats)) < 2:
        why.append("needs 2 identical reads on separate runs from the organisation's own source")
    if not p.get("own"):
        why.append("not the organisation's own source")
    if p.get("conflict"):
        why.append("conflicting source")
    if p.get("known_hours") and p.get("new_empty"):
        why.append("would change known hours to closed or empty")
    if not str(p.get("undo") or "").strip():
        why.append("no logged undo")
    if p.get("field") in LOCKED_FIELDS:
        why.append("phones and council lines are never auto-changed")
    return why


def audit_gaps():
    """Missing guards in the auto-apply sources. Empty means each path names its rail."""
    root = os.path.dirname(os.path.abspath(__file__))
    def src(name):
        return open(os.path.join(root, name), encoding="utf-8").read()
    gaps = []
    disc, tf, fc, pl = src("discover.py"), src("times_finder.py"), src("full_check.py"), src("phone_lock.py")
    if "phones and council lines are never auto-changed" not in disc:
        gaps.append("times gate does not refuse phone and council fields")
    if "times_revert.py" not in disc:
        gaps.append("times gate has no undo command")
    if "2 separate runs" not in disc:
        gaps.append("times gate missing the 2-run check")
    if "closed/empty" not in disc:
        gaps.append("times gate missing the known-hours wipe check")
    if "times_revert.py" not in tf:
        gaps.append("finder has no undo command")
    if "intelligent_rails" not in tf:
        gaps.append("finder does not consult intelligent mode")
    if "never auto-applied" not in fc:
        gaps.append("phone changes can still be auto-applied")
    if "access_revert.py" not in fc:
        gaps.append("access flips have no undo when intelligent mode is on")
    for field in ("council_phone", "council_ooh", "council_label", "council_label_cy"):
        if field not in pl:
            gaps.append("council lock missing " + field)
    return gaps


def transient_fetch(v):
    """A failed page fetch worth trying again. A postcodes.io JSON body is not one of these."""
    if not isinstance(v, dict):
        return False
    if "result" in v and not any(k in v for k in ("http", "ok", "error")):
        return False
    if not any(k in v for k in ("http", "ok", "error")):
        return False
    http = v.get("http")
    if isinstance(http, int) and 200 <= http < 300 and not v.get("error"):
        return False
    if isinstance(http, int) and (http in (403, 408, 425, 429) or http >= 500):
        return True
    err = str(v.get("error") or "")
    if _OUTAGE.search(err):
        return True
    if http in ("error", None) and err:
        return True
    return False


def retry_call(fn, tries=3, sleep=None):
    """Call fn up to `tries` times. A normal return, including postcodes.io JSON, is kept at once.
    The last exception is re-raised. A transient fetch dict is tried again, then returned."""
    delays = _DELAYS if sleep is None else tuple(sleep)
    last = None
    for n in range(max(1, tries)):
        try:
            v = fn()
        except Exception as ex:
            last = ex
            if n + 1 >= tries:
                raise
            time.sleep(delays[n] if n < len(delays) else (delays[-1] if delays else 0))
            continue
        if transient_fetch(v) and n + 1 < tries:
            last = v
            time.sleep(delays[n] if n < len(delays) else (delays[-1] if delays else 0))
            continue
        return v
    return last


def reading_is_outage(home, texts=None):
    """True only for an explicit transient failure. A home dict with no http and no error is a normal read."""
    if not isinstance(home, dict):
        return False
    if home.get("outage") is True:
        return True
    err = str(home.get("error") or "")
    if err and _OUTAGE.search(err):
        return True
    http = home.get("http")
    if "http" not in home and not err:
        return False
    if isinstance(http, int) and (http in (408, 425, 429) or http >= 500):
        return True
    if http in ("error", None) and err:
        return True
    blob = " ".join(t for t in (texts or []) if t)
    if isinstance(http, int) and http == 200 and blob and len(blob) < 400 and _OUTAGE.search(blob):
        return True
    return False


def alert(text, root=None):
    line = "%s: %s" % (ALERT, text)
    print(line, flush=True)
    if not root:
        return line
    try:
        d = os.path.join(root, "reports")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "intelligent_mode.md")
        prev = open(p, encoding="utf-8").read() if os.path.exists(p) else "# Intelligent mode\n"
        if line not in prev:
            open(p, "a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass
    return line


def _recompute(slot):
    steps = slot.get("steps") or {}
    slot["applied"] = sum(int(s.get("applied") or 0) for s in steps.values())
    slot["held"] = sum(int(s.get("held") or 0) for s in steps.values())
    slot["stale_cleared"] = sum(int(s.get("stale_cleared") or 0) for s in steps.values())
    rejected, errors, alerts, cov = [], [], [], {}
    for s in steps.values():
        rejected.extend(s.get("rejected") or [])
        errors.extend(s.get("errors") or [])
        alerts.extend(s.get("alerts") or [])
        cov.update(s.get("coverage") or {})
    slot["rejected"] = rejected[:200]
    slot["errors"] = errors[:80]
    slot["alerts"] = alerts
    slot["coverage"] = cov


def finish(root, layer, step, applied=0, held=0, rejected=None, stale_cleared=0, errors=None, alerts=None, coverage=None):
    """Merge this step into today's summary. A later step does not wipe an earlier one."""
    if not root or not layer or not step:
        return {}
    path = summary_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = load_summary(root)
    if data.get("run") != _today():
        data = {"run": _today(), "layers": {}, "alerts": [], "would_block": []}
    data["enabled"] = bool(data.get("enabled")) or enabled()
    data["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    cov = dict(coverage if coverage is not None else merged(layer, root))
    slot = data.setdefault("layers", {}).setdefault(layer, {"steps": {}})
    slot.setdefault("steps", {})[step] = {
        "applied": int(applied or 0), "held": int(held or 0), "stale_cleared": int(stale_cleared or 0),
        "rejected": list(rejected or [])[:200], "errors": list(errors or [])[:40],
        "alerts": list(alerts or []), "coverage": cov, "enabled": enabled(),
    }
    _recompute(slot)
    blocks = list(data.get("would_block") or [])
    for reason in coverage_reasons(cov):
        line = "coverage gate: " + reason
        if line not in blocks:
            blocks.append(line)
    for line in (alerts or []):
        if line and line not in blocks and str(line).startswith("coverage gate:"):
            blocks.append(line)
    data["would_block"] = blocks
    data["alerts"] = sorted({a for s in data["layers"].values() for a in (s.get("alerts") or [])})
    tmp = path + ".tmp"
    json.dump(data, open(tmp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.replace(tmp, path)
    with _lock:
        _mem[layer] = 0
    return data


def finish_times(root, layer, tlog):
    """One times-step summary. No file on a dry run, so a dry run's reports stay as they were."""
    if os.environ.get("DRY_RUN") or os.environ.get("SAMPLE"):
        return {}
    applied = held = stale = 0
    rejected = []
    for i, rec in (tlog or {}).items():
        if not isinstance(rec, dict):
            continue
        if rec.get("auto_applied"):
            applied += 1
        elif rec.get("status") == "stale_cleared":
            stale += 1
        elif rec.get("status") == "held_for_dean":
            held += 1
            if len(rejected) < 200:
                rejected.append({"id": i, "reasons": list(rec.get("held") or [rec.get("reason") or ""])})
    return finish(root, layer, "times", applied, held, rejected, stale_cleared=stale, coverage=merged(layer, root))


def undone_access(root):
    try:
        raw = json.load(open(os.path.join(root or ".", "overrides", "access_auto_undone.json"), encoding="utf-8"))
    except Exception:
        return set()
    if isinstance(raw, dict):
        return set(raw)
    if isinstance(raw, list):
        return set(raw)
    return set()


def digest_lines(data):
    """Lines for the morning digest. Empty when this run wrote no summary."""
    if not data or (not data.get("layers") and not data.get("would_block") and not data.get("alerts")):
        return []
    L = ["## Intelligent mode", "", "- Switch: %s." % ("on" if data.get("enabled") else "off")]
    seen = set()
    for line in list(data.get("alerts") or []) + list(data.get("would_block") or []):
        if not line or line in seen:
            continue
        seen.add(line)
        L.append("- **%s: %s**" % (ALERT, line) if not str(line).startswith(ALERT) else "- **%s**" % line)
    for name, slot in sorted((data.get("layers") or {}).items()):
        L.append("- %s: applied %d, held %d, rejected %d, stale cleared %d" % (
            name, int(slot.get("applied") or 0), int(slot.get("held") or 0),
            len(slot.get("rejected") or []), int(slot.get("stale_cleared") or 0)))
        for rej in (slot.get("rejected") or [])[:8]:
            L.append("  - %s: %s" % (rej.get("id"), "; ".join(rej.get("reasons") or [])))
        errs = slot.get("errors") or []
        if errs:
            L.append("  - errors: %d (first: %s)" % (len(errs), errs[0]))
        for reason in coverage_reasons(slot.get("coverage") or {}):
            L.append("  - coverage: %s" % reason)
    L.append("")
    return L
