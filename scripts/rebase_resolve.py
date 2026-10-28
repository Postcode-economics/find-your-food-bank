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
- Anything else: keep this run's file (data the run just fetched), as before.
"""
import os, re, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GENERATED_DIRS = ("food-banks/", "warm-spaces/", "shelters/")
GENERATED_FILES = {"sitemap.xml", "robots.txt", "version.json", "overrides/page_dates.json"}
SECTIONED = {"reports/pending_dean.md"}
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


def resolve(f):
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
