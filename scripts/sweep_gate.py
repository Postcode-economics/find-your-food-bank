"""Gate for the sweep push (rule 82, Dean 3 Nov 2026).
The full suite runs on this run's files. A failure blocks the push UNLESS every failing test also fails on a clean
checkout of live main (origin/main) and the failure names a place in a layer file the sweep does not publish and did
not change. That fault is already live and is the refresh's job; the sweep publishes its own outputs and one
'sweep-live-data' alert issue names the place(s). Anything this run caused still blocks. Tests are not changed."""
import json, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LAYERS = [("shelters.js", "Shelters"), ("warmspaces.js", "Warm spaces")]
ALERT_KEY = "sweep-live-data"

def failed_ids(text):
    return sorted(set(re.findall(r"^FAILED (\S+?::\S+)", text, re.M)) | set(re.findall(r"^ERROR (\S+?::\S+)", text, re.M)))

def _load(text):
    return json.loads(text[text.index("=") + 1:].strip().rstrip(";"))

def _keys(item):
    out = {str(item.get("id") or "")}
    for v in item.values():
        if isinstance(v, str) and len(v.strip()) >= 15: out.add(v.strip()[:30])
    return {k for k in out if len(k) >= 6}

def places_named(text, layer_items):
    """[(layer title, id, name)] for cards whose id or a text field shows in the failure output."""
    return [(t, i["id"], i.get("name") or i["id"]) for t, items in layer_items for i in items
            if i.get("id") and any(k in text for k in _keys(i))]

def published_by_sweep(workflow_text):
    return {w for l in workflow_text.splitlines() if "git_add_existing.sh" in l or l.strip().endswith("\\") for w in l.split()}

def decide(fail_ids, live_fail_ids, changed_layers, published, named):
    """Pure decision. Returns (ok_to_publish, places)."""
    if not fail_ids: return True, []
    if set(fail_ids) - set(live_fail_ids): return False, []            # this run caused a failure
    places = [p for p in named if p[0] not in changed_layers]
    files = {f for f, t in LAYERS}
    if any(f in published for f in files): return False, []             # sweep would publish layer data: block
    if not places: return False, []                                     # cannot tie it to a live place: block
    return True, places

def run(py, args, cwd="."):
    r = subprocess.run([py, "-m", "pytest", "-q", "-rf", "--tb=short", "-p", "no:cacheprovider"] + args, cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr

def main():
    py = sys.argv[1] if len(sys.argv) > 1 else sys.executable
    code, text = run(py, ["tests"])
    print(text[-6000:])
    import alert
    if code == 0:
        try: alert.resolve(ALERT_KEY)
        except Exception as e: print("alert resolve failed:", e)
        return 0
    fails = failed_ids(text)
    if not fails: return 1
    live_dir = tempfile.mkdtemp(prefix="live-main-")
    subprocess.run(["git", "worktree", "add", "--detach", live_dir, "origin/main"], check=True, capture_output=True)
    try:
        _, live_text = run(py, fails, cwd=live_dir)
        live_fails = failed_ids(live_text)
        changed, layer_items = set(), []
        for f, t in LAYERS:
            live = subprocess.run(["git", "show", "origin/main:" + f], capture_output=True, text=True).stdout
            if not live: continue
            items = _load(live).get("items", [])
            layer_items.append((t, items))
            # "Changed" = differs from live beyond the local repair step. Compare against live after the same repair.
            subprocess.run([sys.executable, "scripts/fill_referral_routes.py"], cwd=live_dir, capture_output=True)
            if open(os.path.join(live_dir, f), encoding="utf-8").read() != open(f, encoding="utf-8").read(): changed.add(t)
        wf = open(".github/workflows/sweep-daily.yml", encoding="utf-8").read()
        ok, places = decide(fails, live_fails, changed, published_by_sweep(wf), places_named(text, layer_items))
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", live_dir], capture_output=True)
    if not ok:
        print("BLOCK: failing tests this run caused or that are not tied to an unchanged, unpublished layer:", fails)
        return 1
    lines = "\n".join("- %s: %s (%s)" % p for p in places)
    body = ("The sweep published its own outputs. These live listings fail a check in data the sweep does not change or publish, "
            "so the fault is already live and needs fixing in the refresh or by hand. Live data was not changed.\n\n" + lines +
            "\n\nFailing tests (also failing on live main):\n" + "\n".join("- " + f for f in fails))
    alert.open_(ALERT_KEY, "Live listing fails a check (sweep still published)", body)
    print("PUBLISH: failures are pre-existing live-data faults in unpublished layer files:", places)
    return 0

if __name__ == "__main__":
    sys.exit(main())
