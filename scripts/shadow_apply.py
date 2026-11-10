"""Shadow mode for proposed automatic rules (Grok Bot 2, 9 Nov 2026).

Runs a proposed decision against today's candidates and writes what *would*
have been applied to private reports/shadow/, without changing overlays,
published data, phones or locks. Used for the two-week shadow period before
any Phase 2 rule goes live. Fail-closed: any error skips the item.
"""
from __future__ import annotations

import datetime, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = "reports/shadow"


def _today():
    return datetime.date.today().isoformat()


def shadow_run(rule_id, candidates, decide, root=None, write=True, meta=None):
    """Evaluate decide(candidate) -> ('apply'|'hold', reason, detail).

    decide must be pure with respect to overlays: this harness never writes
    overrides/, data files, or phone fields. Returns the shadow report dict.
    """
    root = root or ROOT
    day = _today()
    applied, held, errors = [], [], []
    for c in candidates or []:
        try:
            decision, reason, detail = decide(c)
        except Exception as ex:
            errors.append({"id": (c or {}).get("id"), "error": str(ex)[:160]})
            continue
        row = {
            "id": (c or {}).get("id"),
            "name": (c or {}).get("name"),
            "decision": decision,
            "reason": reason,
            "detail": detail or {},
        }
        if decision == "apply":
            applied.append(row)
        else:
            held.append(row)
    report = {
        "day": day,
        "rule_id": rule_id,
        "mode": "shadow",
        "meta": meta or {},
        "would_apply": applied,
        "would_hold": held,
        "errors": errors,
        "summary": {
            "candidates": len(candidates or []),
            "would_apply": len(applied),
            "would_hold": len(held),
            "errors": len(errors),
        },
        "note": (
            "Shadow only. Nothing was published or written to overlays. "
            "Compare against the 08:00 hand-check before asking Dean to turn a Phase 2 rule on."
        ),
    }
    if write:
        dest = os.path.join(root, OUT_DIR)
        os.makedirs(dest, exist_ok=True)
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in (rule_id or "rule"))
        path = os.path.join(dest, "%s_%s.json" % (day, safe))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")
        report["path"] = path
    return report


def assert_no_overlay_writes(before_listing, root):
    """Helper for tests: overlay paths must be unchanged."""
    after = []
    ov = os.path.join(root, "overrides")
    if os.path.isdir(ov):
        for dirpath, _, files in os.walk(ov):
            for fn in files:
                after.append(os.path.relpath(os.path.join(dirpath, fn), root))
    return sorted(before_listing) == sorted(after)


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    print("shadow_apply: library module. Import shadow_run(rule_id, candidates, decide).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
