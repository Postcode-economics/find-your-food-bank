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
  start from main's copy and apply only the sections this run changed.
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


def merge_sections(base, ours, theirs):
    """main's text (ours) plus every section this run (theirs) changed versus base."""
    b, t = sections(base), sections(theirs)
    out = ours
    for tag, block in t.items():
        if b.get(tag) == block:
            continue  # this run didn't touch it: main's version stands
        cur = sections(out).get(tag)
        if cur is not None:
            out = out.replace(cur, block if block.endswith("\n") or not cur.endswith("\n") else block + "\n", 1)
        else:
            out = out.rstrip("\n") + "\n\n" + (block if block.endswith("\n") else block + "\n")
    return out


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
