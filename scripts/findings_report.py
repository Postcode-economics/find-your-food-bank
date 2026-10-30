"""Post a plain-English findings summary as a GitHub issue comment (Dean, Oct 2026).

Each refresh/sweep workflow calls:  python scripts/findings_report.py <foodbanks|warmspaces|shelters|sweep>

When the run found something genuinely new, the script comments on a long-lived issue labelled
'findings-report' (created if missing). GitHub emails @Postcode-economics for each comment.
If nothing new, it posts nothing. Errors are logged and never fail the workflow step."""
import datetime, json, os, re, subprocess, sys
from zoneinfo import ZoneInfo

ROOT = os.path.join(os.path.dirname(__file__), "..")
LABEL = "findings-report"
RUN = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
UK = ZoneInfo("Europe/London")

WORKFLOWS = {
    "foodbanks": {"key": "findings-foodbanks", "title": "Findings report: Food bank refresh", "layers": ["foodbanks"]},
    "warmspaces": {"key": "findings-warmspaces", "title": "Findings report: Warm spaces refresh", "layers": ["warmspaces"]},
    "shelters": {"key": "findings-shelters", "title": "Findings report: Shelters refresh", "layers": ["shelters"]},
    "sweep": {"key": "findings-sweep", "title": "Findings report: Daily deep sweep", "layers": ["sweep"]},
}
LAYER_NAMES = {"foodbanks": "Food banks", "shelters": "Shelters", "warmspaces": "Warm spaces", "sweep": "Deep sweep"}
LINE_CAP = 30
_SECTION = re.compile(r"(?s)<!-- (?P<tag>[^>]+) -->.*?<!-- /(?P=tag) -->")
_PENDING_LINE = re.compile(r"^- (.+)$")


class ReportError(Exception):
    pass


def _load(path, root=None):
    p = os.path.join(root or ROOT, path)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _read(path, root=None):
    p = os.path.join(root or ROOT, path)
    try:
        return open(p, encoding="utf-8").read()
    except Exception:
        return ""


def _git_show(ref, path, root=None):
    root = root or ROOT
    if not ref:
        return None
    try:
        return subprocess.check_output(["git", "-C", root, "show", f"{ref}:{path}"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return None


def baseline_ref(root=None):
    ref = os.environ.get("FINDINGS_BASELINE_REF", "").strip()
    if ref:
        return ref
    root = root or ROOT
    try:
        return subprocess.check_output(
            ["git", "-C", root, "rev-parse", "HEAD^"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return None


def parse_run_start():
    raw = os.environ.get("GITHUB_RUN_STARTED_AT") or os.environ.get("FINDINGS_RUN_STARTED_AT") or ""
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _iso(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def cap_lines(lines, limit=LINE_CAP):
    lines = [x for x in lines if x]
    if len(lines) <= limit:
        return lines, 0
    return lines[:limit], len(lines) - limit


def section_text(md, tag):
    m = _SECTION.search(md or "")
    if not m or m.group("tag") != tag:
        return ""
    return m.group(0)


def section_body(md, tag):
    m = _SECTION.search(md or "")
    if not m or m.group("tag") != tag:
        return []
    block = m.group(0)
    inner = block.split("-->", 1)[-1].rsplit("<!--", 1)[0].strip()
    return [ln.strip() for ln in inner.splitlines() if ln.strip().startswith("- ")]


def pending_ids(blob):
    if not blob:
        return set()
    out = set()
    for layer in blob:
        if layer.startswith("_"):
            continue
        for row in blob.get(layer) or []:
            if row.get("id"):
                out.add(row["id"])
    return out


def publish_new_ids(layer, root, ref):
    sys.path.insert(0, os.path.join(root, "scripts"))
    import discovery_rules as DR

    if layer != "foodbanks":
        return None
    rel = DR._LAYER_FILES.get(layer)
    if not rel:
        return []
    cur = {i["id"] for i in DR._items_from_js(os.path.join(root, rel)) if i.get("id")}
    raw = _git_show(ref, rel, root) if ref else None
    if not raw:
        return []
    try:
        prev = {i["id"] for i in DR._items_from_js(raw) if i.get("id")}
    except Exception:
        prev = set()
    return sorted(cur - prev)


def _published_at_ref(layer, root, ref):
    sys.path.insert(0, os.path.join(root, "scripts"))
    import discovery_rules as DR

    if layer == "sweep":
        out = set()
        for ly in ("shelters", "warmspaces"):
            out |= _published_at_ref(ly, root, ref)
        return out
    rel = DR._LAYER_FILES.get(layer)
    if not rel:
        return set()
    raw = _git_show(ref, rel, root) if ref else None
    if raw:
        try:
            return {i["id"] for i in DR._items_from_js(raw) if i.get("id")}
        except Exception:
            pass
    return DR.published_ids(layer, root)


def new_published(layer, root, ref):
    sys.path.insert(0, os.path.join(root, "scripts"))
    import discovery_rules as DR

    logp = f"logs/discovery_today_{layer}.json"
    log = _load(logp, root) or {}
    added = list(log.get("added") or [])
    kwargs = {"root": root}
    if ref:
        kwargs["baseline_ids"] = _published_at_ref(layer, root, ref)
    if layer == "foodbanks":
        kwargs["publish_new_ids"] = publish_new_ids(layer, root, ref)
    kept = DR.filter_added(layer, added, **kwargs)
    lines = []
    for a in kept:
        pc = a.get("postcode") or "?"
        lines.append(f"- {a.get('name', '?')} ({pc}) — {LAYER_NAMES.get(layer, layer)}")
    return lines


def discovery_queued_new(layer, root, ref):
    path = f"logs/discovery_today_{layer}.json"
    cur = _load(path, root) or {}
    prev = None
    raw = _git_show(ref, path, root)
    if raw:
        try:
            prev = json.loads(raw)
        except Exception:
            prev = {}
    prev = prev or {}
    new_keys = set((cur.get("queued") or {}).keys()) - set((prev.get("queued") or {}).keys())
    lines = []
    for k in sorted(new_keys):
        e = (cur.get("queued") or {}).get(k) or {}
        bits = [e.get("name", "?")]
        if e.get("postcode"):
            bits.append(e["postcode"])
        why = "; ".join(e.get("reasons") or [])[:120]
        lines.append(f"- {' · '.join(bits)} — {LAYER_NAMES.get(layer, layer)} queue" + (f" ({why})" if why else ""))
    return lines


def pending_new(root, ref):
    cur = _load("logs/pending_dean.json", root) or {}
    prev = {}
    raw = _git_show(ref, "logs/pending_dean.json", root) if ref else None
    if raw:
        try:
            prev = json.loads(raw)
        except Exception:
            prev = {}
    new_ids = pending_ids(cur) - pending_ids(prev)
    lines = []
    for layer, rows in (cur or {}).items():
        if layer.startswith("_") or not isinstance(rows, list):
            continue
        for row in rows:
            if row.get("id") in new_ids:
                why = ", ".join(row.get("why") or [])[:140]
                lines.append(
                    f"- {row.get('name', '?')} ({row.get('postcode') or '?'}) — waiting ({layer}): {why}"
                )
    return lines


def sweep_shelter_new(root, ref):
    cur = _read("reports/pending_dean.md", root)
    prev_md = _git_show(ref, "reports/pending_dean.md", root) if ref else ""
    cur_lines = set(section_body(cur, "sweep shelters"))
    prev_lines = set(section_body(prev_md or "", "sweep shelters"))
    new = sorted(cur_lines - prev_lines)
    return [x for x in new if x not in ("- none", "- none this run")]


def times_summary(entry):
    def pick(obj):
        if not obj:
            return "none"
        if isinstance(obj, dict):
            if obj.get("raw"):
                return str(obj["raw"]).replace("\n", " ")[:120]
            st = obj.get("structured")
            if st:
                return json.dumps(st, ensure_ascii=False)[:120]
        return str(obj)[:120]

    old = entry.get("old")
    if old is None and "old_structured" in entry:
        old = entry.get("old_structured")
    new = entry.get("new") or entry.get("new_structured")
    return f"{pick(old)} -> {pick(new)}"


def times_applied_this_run(root, run_start):
    log = _load("reports/times_auto_applied.json", root)
    if not isinstance(log, list) or not run_start:
        return []
    out = []
    for e in log:
        ts = _iso(e.get("second_run_at"))
        if not ts or ts < run_start - datetime.timedelta(minutes=3):
            continue
        if e.get("hand_reviewed"):
            continue
        name = e.get("name") or e.get("id") or "?"
        out.append(f"- {name}: {times_summary(e)}")
    return out


def phone_lock_new(root, ref):
    cur = section_body(_read("reports/pending_dean.md", root), "phone lock")
    prev = section_body(_git_show(ref, "reports/pending_dean.md", root) or "", "phone lock")
    return sorted(set(cur) - set(prev))


def held_items(root, layers):
    data = _load("reports/intelligent_mode.json", root) or {}
    lines = []
    total = 0
    for layer in layers:
        slot = (data.get("layers") or {}).get(layer) or {}
        rejected = slot.get("rejected") or []
        if not rejected and not slot.get("held"):
            continue
        total += int(slot.get("held") or 0) or len(rejected)
        for rej in rejected:
            rid = rej.get("id") or "?"
            rs = "; ".join(rej.get("reasons") or [])[:160]
            lines.append(f"- {rid}: {rs}")
    lines, extra = cap_lines(lines)
    header = f"Items held this run ({total} total)"
    if extra:
        header += f" — showing {len(lines)}, and {extra} more"
    return [header] + lines if lines else []


def swep_changes(root):
    lr = _load("reports/layers_review.json", root) or {}
    changes = (lr.get("swep") or {}).get("changes") or []
    sw = _load("logs/swep_status.json", root) or {}
    changes = changes or sw.get("changes") or []
    return [
        f"- {c.get('council', '?')}: {c.get('from', '?')} -> {c.get('to', '?')}"
        for c in changes
    ]


def coverage_line(root, layers):
    sys.path.insert(0, os.path.join(root, "scripts"))
    try:
        import intelligent_rails as IR
    except Exception:
        return ""
    data = _load("reports/intelligent_mode.json", root) or {}
    bits = []
    for layer in layers:
        cov = ((data.get("layers") or {}).get(layer) or {}).get("coverage") or IR.merged(layer, root)
        if not cov:
            continue
        reasons = IR.coverage_reasons(cov)
        if reasons:
            bits.append(f"{layer}: " + "; ".join(reasons))
        else:
            sp, so = cov.get("source_pages"), cov.get("source_opened")
            att, err = cov.get("render_attempts"), cov.get("render_errors")
            chunk = []
            if isinstance(sp, int) and sp:
                chunk.append("sources %d/%d opened" % (so or 0, sp))
            if isinstance(att, int) and att:
                chunk.append("render errors %d/%d" % (err or 0, att))
            if chunk:
                bits.append(f"{layer}: " + ", ".join(chunk))
    return "Coverage: " + " · ".join(bits) if bits else ""


def build_report(workflow, root=None, ref=None, run_started=None, run_url=None):
    root = root or ROOT
    meta = WORKFLOWS.get(workflow)
    if not meta:
        raise ReportError(f"unknown workflow {workflow!r}")
    ref = ref if ref is not None else baseline_ref(root)
    run_started = run_started if run_started is not None else parse_run_start()
    run_url = run_url or RUN
    layers = meta["layers"]
    sections = []

    published = []
    for layer in layers:
        published.extend(new_published(layer, root, ref))
    if published:
        body, extra = cap_lines(published)
        head = f"NEW places published ({len(published)})"
        if extra:
            head += f" — showing {len(body)}, and {extra} more"
        sections.append(head + "\n" + "\n".join(body))

    candidates = pending_new(root, ref)
    for layer in layers:
        candidates.extend(discovery_queued_new(layer, root, ref))
    if workflow == "sweep":
        candidates.extend(sweep_shelter_new(root, ref))
    if candidates:
        body, extra = cap_lines(candidates)
        head = f"New candidates for review ({len(candidates)})"
        if extra:
            head += f" — showing {len(body)}, and {extra} more"
        sections.append(head + "\n" + "\n".join(body))

    applied = times_applied_this_run(root, run_started)
    if applied:
        body, extra = cap_lines(applied)
        head = f"Opening times auto-applied this run ({len(applied)})"
        if extra:
            head += f" — showing {len(body)}, and {extra} more"
        sections.append(head + "\n" + "\n".join(body))

    held = held_items(root, layers)
    if held:
        sections.append("\n".join(held))

    phones = phone_lock_new(root, ref)
    if phones:
        body, extra = cap_lines(phones)
        head = f"Phone / council-line holds (phone lock) ({len(phones)})"
        if extra:
            head += f" — showing {len(body)}, and {extra} more"
        sections.append(head + "\n" + "\n".join(body))

    if workflow == "shelters":
        swep = swep_changes(root)
        if swep:
            sections.append("SWEP status changes\n" + "\n".join(swep))

    if not sections:
        return None

    cov = coverage_line(root, layers)
    if cov:
        sections.append(cov)

    when = datetime.datetime.now(UK).strftime("%d %b %Y %H:%M %Z")
    header = f"## {meta['title']}\n\nTime (UK): {when}\nRun: {run_url}\n"
    return header + "\n\n" + "\n\n".join(sections) + "\n"


def gh(*a):
    r = subprocess.run(["gh", *a], capture_output=True, text=True)
    if r.returncode != 0:
        raise ReportError(f"gh {a[0]} failed: {r.stderr.strip()[:300]}")
    return r


def find_issue(key):
    r = gh("issue", "list", "--label", LABEL, "--state", "open", "--json", "number,title", "--limit", "1000")
    return next((i["number"] for i in json.loads(r.stdout or "[]") if f"[{key}]" in i["title"]), None)


def post(key, title, body):
    gh("label", "create", LABEL, "--color", "0E8A16", "--description", "Automatic findings after refresh/sweep", "--force")
    n = find_issue(key)
    if n:
        gh("issue", "comment", str(n), "--body", body)
    else:
        gh("issue", "create", "--title", f"[{key}] {title}", "--label", LABEL, "--body", body)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"Findings report posted to issue {'#' + str(n) if n else '(new)'}\n")
    print(f"FINDINGS [{key}] -> issue {'#' + str(n) if n else 'created'}")


def deliver(workflow, root=None, ref=None, run_started=None, run_url=None, post_fn=post):
    text = build_report(workflow, root=root, ref=ref, run_started=run_started, run_url=run_url)
    if not text:
        print(f"FINDINGS [{workflow}] nothing new — no comment posted")
        return 0
    meta = WORKFLOWS[workflow]
    post_fn(meta["key"], meta["title"], text)
    return 0


def main(argv=None):
    argv = argv or sys.argv
    wf = argv[1] if len(argv) > 1 else ""
    if wf not in WORKFLOWS:
        print(f"::warning::findings_report.py: unknown workflow {wf!r}", file=sys.stderr)
        return 0
    try:
        return deliver(wf)
    except Exception as e:
        print(f"::warning::findings_report.py failed (ignored): {type(e).__name__}: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
