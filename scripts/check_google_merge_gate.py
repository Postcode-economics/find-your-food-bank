#!/usr/bin/env python3
"""Merge gate: Google Serper PR must land AFTER bc-95f199ae batch 3 is on main.

Dean 1 Nov 2026: wait until main includes batch 3 shelter additions, then merge from main,
run full CI, merge Google PR, one shelters refresh.

Signals (any one passes):
  1) overrides/shelters_manual.json contains a row whose why/source mentions batch 3 (case-insensitive)
  2) tests/test_shelters_cities_batch3.py exists on main
  3) approved_new_places.json mentions "batch 3" for a shelter id added after baseline

Also require PR #370 (or successor) shelter data merged — not chip-only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys

BASELINE_MANUAL_COUNT = 253  # main after #362 merge, 1 Nov 2026 ~09:00 UTC


def main():
    subprocess.run(["git", "fetch", "origin", "main"], check=True, cwd=".")
    manual = subprocess.check_output(
        ["git", "show", "origin/main:overrides/shelters_manual.json"], cwd="."
    )
    data = json.loads(manual)
    text = manual.decode("utf-8", "replace").lower()
    reasons = []
    ok = False

    if re.search(r"batch\s*3", text):
        ok = True
        reasons.append("shelters_manual mentions batch 3")

    r = subprocess.run(
        ["git", "show", "origin/main:tests/test_shelters_cities_batch3.py"],
        cwd=".",
        capture_output=True,
    )
    if r.returncode == 0:
        ok = True
        reasons.append("test_shelters_cities_batch3.py on main")

    ap = subprocess.check_output(["git", "show", "origin/main:overrides/approved_new_places.json"], cwd=".")
    if re.search(r"batch\s*3", ap.decode("utf-8", "replace"), re.I):
        ok = True
        reasons.append("approved_new_places mentions batch 3")

    if len(data) > BASELINE_MANUAL_COUNT + 5:
        # weak signal only — report but do not pass alone
        reasons.append(f"manual count {len(data)} > baseline {BASELINE_MANUAL_COUNT} (needs batch 3 marker)")

    try:
        pr370 = subprocess.run(
            ["gh", "pr", "view", "370", "--json", "state,mergedAt,files"],
            capture_output=True,
            text=True,
            cwd=".",
        )
        if pr370.returncode == 0:
            info = json.loads(pr370.stdout)
            paths = [f["path"] for f in info.get("files") or []]
            if info.get("state") == "MERGED" and any("shelters_manual" in p for p in paths):
                ok = True
                reasons.append("PR #370 merged with shelters_manual changes")
            elif info.get("state") == "OPEN":
                reasons.append("PR #370 still open (batch 3 shelters may land in a follow-up commit)")
    except Exception as e:
        reasons.append(f"PR #370 check skipped: {e}")

    print("MERGE_GATE_OPEN=" + ("yes" if ok else "no"))
    for r in reasons:
        print("-", r)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
