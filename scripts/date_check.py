#!/usr/bin/env python3
"""Date-consistency check, ALERT-ONLY (Dean, 27 Oct 2026: alert for one week before it can fail).

Compares the times shown on built pages with the shared source, stamp.js (window.FB_STAMP):
  * "Information last updated <label>" on food-banks/, shelters/, warm-spaces/ pages must equal
    that layer's label (fb, sh, ws).
  * "Map data last checked <label>" (the mapchk line, with its data-run) must equal the newest
    layer, i.e. FB_STAMP.label / FB_STAMP.run.
  * "Phone numbers and opening times checked <date>" must show one and the same date on every
    page that has it (no separate shared stamp exists on main yet).
Mismatches are printed as GitHub ::warning:: lines and written to the job summary.
It ALWAYS exits 0, so it never fails CI. Pass --strict to get a non-zero exit (for later).
"""
import json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAYER_DIRS = {"food-banks": "fb", "shelters": "sh", "warm-spaces": "ws"}
DATE = r"\d{1,2} [A-Z][a-z]{2} \d{4}(?:, \d{2}:\d{2})?"
RE_INFO = re.compile(r"Information last updated (" + DATE + r")")
RE_MAP = re.compile(r'class="mapchk"(?: data-run="([^"]*)")?>Map data last checked (' + DATE + r")")
RE_PHONE = re.compile(r"Phone numbers and opening times checked (" + DATE + r")")


def load_stamp(root):
    txt = (root / "stamp.js").read_text(encoding="utf-8")
    return json.loads(txt[txt.index("{"):txt.rindex("}") + 1])


def check(root=ROOT):
    root = Path(root)
    st = load_stamp(root)
    layers = st.get("layers", {})
    problems = []
    phone_seen = {}
    for page in sorted(root.rglob("*.html")):
        rel = page.relative_to(root).as_posix()
        if rel.startswith(("vendor/", "tests/", ".git/", "node_modules/")):
            continue
        html = page.read_text(encoding="utf-8", errors="replace")
        top = rel.split("/", 1)[0]
        key = LAYER_DIRS.get(top)
        if key and key in layers:
            want = layers[key].get("label")
            for got in set(RE_INFO.findall(html)):
                if got != want:
                    problems.append(f"{rel}: 'Information last updated {got}' but stamp.js {key} says '{want}'")
        for run, got in set(RE_MAP.findall(html)):
            if got != st.get("label") or (run and run != st.get("run")):
                problems.append(f"{rel}: 'Map data last checked {got}' (run {run or '-'}) but stamp.js newest is '{st.get('label')}' (run {st.get('run')})")
        for got in set(RE_PHONE.findall(html)):
            phone_seen.setdefault(got, []).append(rel)
    if len(phone_seen) > 1:
        common = max(phone_seen, key=lambda k: len(phone_seen[k]))
        for got, pages in sorted(phone_seen.items()):
            if got != common:
                for rel in pages:
                    problems.append(f"{rel}: 'Phone numbers and opening times checked {got}' but most pages say '{common}'")
    return problems


def main(argv):
    problems = check(ROOT)
    for p in problems:
        print(f"::warning title=date check (alert-only)::{p}")
    head = f"Date check (alert-only): {len(problems)} mismatch(es)"
    print(head)
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write(f"### {head}\n\n" + "".join(f"- {p}\n" for p in problems[:200]))
    return 1 if (problems and "--strict" in argv) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
