#!/usr/bin/env python3
"""Resolve conflicts left by `git pull --rebase` in a refresh or sweep.

During a rebase, stage :2 is main (upstream, already merged PRs) and stage :3 is
this run's commit being replayed.

- stamp.js: keep the later date of each layer (scripts/stamp.py combine-index).
- Generated pages (HTML, area pages, sitemap, page dates...): keep MAIN's copy.
  The workflow rebuilds them with build_seo.py + seo_meta.py straight after, so this
  run's dates still land, but a run that started before a PR merged can never put
  back its stale copy of a page that PR changed (28 Oct: sweep 97bcb4149 reverted
  #212's faq.html this way).
- Sectioned reports (<!-- tag --> ... <!-- /tag -->, e.g. reports/pending_dean.md):
  three-way merge by chunk: each section and the free text around it (such as the
  header above the first section) keeps this run's version where the run changed it,
  else main's; a section the run removed stays removed.
- Automatic-change undo logs and seen/undone maps (UNDO_LOGS, KEYED): merged by JSON content, so one
  layer's run never drops another layer's undo entries or two-run readings.
- Anything else: keep this run's file (data the run just fetched), as before.
"""
import json, os, re, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GENERATED_DIRS = ("food-banks/", "warm-spaces/", "shelters/")
GENERATED_FILES = {"sitemap.xml", "robots.txt", "version.json", "overrides/page_dates.json"}
SECTIONED = {"reports/pending_dean.md"}
# Shared automatic-change state, written by more than one workflow (.gitattributes marks them -merge, so any change on
# both sides comes here). Undo logs are append-only lists: every entry from both sides is kept once. Seen/undone files are
# maps: each key the run changed takes the run's value, every other key keeps main's.
UNDO_LOGS = {"reports/times_auto_applied.json", "reports/phone_auto_applied.json"}
KEYED = {"logs/times_crosscheck_seen.json", "logs/times_finder_seen.json",
         "overrides/times_auto_undone.json", "overrides/phone_auto_undone.json"}
SEC = re.compile(r"<!-- (?!/)([\w .-]+?) -->\n.*?<!-- /\1 -->\n?", re.S)


def is_generated(f):
    return f.endswith(".html") or f in GENERATED_FILES or f.startswith(GENERATED_DIRS)


def git(*a, check=True):
    return subprocess.run(["git", *a], cwd=ROOT, check=check, capture_output=True, text=True)


def stage(f, n):
    r = git("show", ":%d:%s" % (n, f), check=False)
    return r.stdout if r.returncode == 0 else None


def sections(text):
    return {m.group(1): m.group(0) for m in SEC.finditer(text or "")}


def chunks(text):
    """Split a sectioned report into ordered chunks: "^" is the free text before the
    first section (e.g. the "New places held back for Dean" header), each section is
    keyed by its tag, and ">tag" is the free text after that section."""
    text = text or ""
    out, pos, key = [], 0, "^"
    for m in SEC.finditer(text):
        out.append((key, text[pos:m.start()]))
        out.append((m.group(1), m.group(0)))
        pos, key = m.end(), ">" + m.group(1)
    out.append((key, text[pos:]))
    return out


def merge_sections(base, ours, theirs):
    """Three-way merge by chunk (sections AND the free text between them).

    For each chunk: if this run (theirs) changed it versus base, the run's version
    wins (including deleting it); otherwise main's (ours) stands. A chunk the run
    deleted is dropped unless main also edited it (then main's edit is kept, so
    nothing main added is lost). Chunks new in the run are added after main's."""
    b, t = dict(chunks(base)), dict(chunks(theirs))
    o_list = chunks(ours)
    o_keys = {k for k, _ in o_list}
    out = []
    for k, v in o_list:
        bv, tv = b.get(k), t.get(k)
        if k in b and k not in t:          # run removed it
            if v == bv:
                continue                   # main didn't touch it: stays removed
            out.append(v)                  # main edited it: keep main's edit
        elif k in t and tv != bv:
            out.append(tv)                 # run changed it
        else:
            out.append(v)
    for k, v in chunks(theirs):
        if k in o_keys or k in b:
            continue                       # handled above (or main removed it)
        if out and not "".join(out).endswith("\n"):
            out.append("\n")
        if not k.startswith(">") and "".join(out).strip():
            out.append("\n")
        out.append(v)
    return "".join(out)


def _json(text, default):
    try: return json.loads(text) if text else default
    except ValueError: return default


def merge_undo_log(base, ours, theirs):
    """Union of both sides' entries, main's order first. An entry reverted on either side stays reverted."""
    key = lambda e: json.dumps({k: v for k, v in e.items() if k != "reverted"}, sort_keys=True)
    out, at = [], {}
    for e in (_json(ours, []) or []) + (_json(theirs, []) or []):
        if not isinstance(e, dict): continue
        k = key(e)
        if k in at:
            if e.get("reverted"): out[at[k]]["reverted"] = True
            continue
        at[k] = len(out); out.append(dict(e))
    return out


def merge_keyed(base, ours, theirs):
    """Three-way merge by key: the run's change to a key wins, otherwise main's value stands."""
    b, o, t = (_json(x, {}) or {} for x in (base, ours, theirs))
    out = dict(o)
    for k, v in t.items():
        if b.get(k, object()) != v: out[k] = v
    for k in b:
        if k not in t and o.get(k) == b[k]: out.pop(k, None)
    return out


def resolve(f):
    if f in UNDO_LOGS or f in KEYED:
        ours, theirs = stage(f, 2), stage(f, 3)
        merged = (merge_undo_log if f in UNDO_LOGS else merge_keyed)(stage(f, 1), ours, theirs)
        with open(os.path.join(ROOT, f), "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=1 if f in UNDO_LOGS else 0, sort_keys=f in KEYED, ensure_ascii=False)
        git("add", "--", f); return "json-merge"
    if f == "stamp.js":
        subprocess.run([sys.executable, "scripts/stamp.py", "combine-index"], cwd=ROOT, check=True)
        git("add", "--", f); return "stamp"
    ours, theirs = stage(f, 2), stage(f, 3)
    if is_generated(f):
        if ours is None:
            git("rm", "-q", "--", f); return "main-deleted"
        git("checkout", "--ours", "--", f); git("add", "--", f); return "main"
    if f in SECTIONED and ours is not None and theirs is not None:
        with open(os.path.join(ROOT, f), "w", encoding="utf-8") as fh:
            fh.write(merge_sections(stage(f, 1) or "", ours, theirs))
        git("add", "--", f); return "sections"
    if theirs is not None:
        git("checkout", "--theirs", "--", f); git("add", "--", f); return "run"
    git("rm", "-q", "--", f); return "run-deleted"


def main():
    files = [x for x in git("diff", "--name-only", "--diff-filter=U").stdout.split("\n") if x]
    for f in files:
        print("conflict %s -> %s" % (f, resolve(f)))


if __name__ == "__main__":
    main()
