#!/usr/bin/env python3
"""Batch 3: verify new Serper towns every 30s until Serper finished or all towns Googled."""
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "logs" / "google_serper_state.json"
SERPER_LOG = ROOT / "logs" / "serper_run.log"
ALL_TOWNS = ROOT / "data" / "all_towns.txt"
LOG_MD = ROOT / "google_log.md"
BATCH1 = ROOT / "logs" / "google_verify_batch1.txt"
BATCH2 = ROOT / "logs" / "google_verify_batch2.txt"
BATCH3 = ROOT / "logs" / "google_verify_batch3.txt"

import sys

sys.path.insert(0, str(ROOT / "scripts"))
from google_serper_verify_town import verify_town


def parse_batch_towns(path):
    towns = set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^  (.+): (\d+) / (\d+)\s*$", line)
        if m:
            towns.add(m.group(1))
    return towns


def googled_in_md():
    done = set()
    in_done = False
    text = LOG_MD.read_text(encoding="utf-8") if LOG_MD.exists() else ""
    for line in text.splitlines():
        if line.startswith("## Googled"):
            in_done = True
            continue
        if line.startswith("## ") and in_done:
            in_done = False
        if in_done and line.startswith("- "):
            done.add(line[2:].strip())
    return done


def all_towns_list():
    out = []
    for line in ALL_TOWNS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def serper_finished():
    if not SERPER_LOG.exists():
        return False
    try:
        tail = SERPER_LOG.read_text(encoding="utf-8", errors="replace")[-8000:]
    except OSError:
        return False
    return "Finished batch" in tail


def stop_condition():
    if serper_finished():
        return True, "serper Finished batch"
    done = googled_in_md()
    all_t = set(all_towns_list())
    if all_t and all_t <= done:
        return True, "all towns in google_log.md Googled"
    return False, ""


def already_verified():
    return parse_batch_towns(BATCH1) | parse_batch_towns(BATCH2)


def main():
    verified_batches = already_verified()
    stats_path = ROOT / "logs" / "batch3_stats.json"
    if stats_path.exists():
        batch3_stats = json.loads(stats_path.read_text(encoding="utf-8"))
    else:
        batch3_stats = {}

    print("Batch3 loop start. Already in batch1+2:", len(verified_batches))
    iteration = 0
    while True:
        iteration += 1
        state = json.loads(STATE.read_text(encoding="utf-8"))
        in_state = set(state.get("towns") or {})
        pending = sorted(t for t in in_state if t not in verified_batches and t not in batch3_stats)

        if pending:
            print(f"[{iteration}] verify {len(pending)} pending (e.g. {pending[:3]})")
            for town in pending:
                blocks = state["towns"][town]
                r = verify_town(town, blocks)
                batch3_stats[town] = {"a": r["a_added"], "b": r["b_added"]}
                if r["a_added"]:
                    print(f"  A: {town} -> {r['a_entry'].get('name')}")
            stats_path.write_text(json.dumps(batch3_stats, indent=2), encoding="utf-8")
        else:
            print(f"[{iteration}] no new towns in state to verify")

        done, reason = stop_condition()
        if done:
            print("Stop:", reason)
            break
        time.sleep(30)

    write_summary(batch3_stats)
    stats_path.write_text(json.dumps(batch3_stats, indent=2), encoding="utf-8")
    return 0


def write_summary(batch3_stats):
    held = json.loads((ROOT / "held_google.json").read_text()).get("held") or []
    a_items = json.load(open(ROOT / "logs" / "google_a_items.json", encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8"))
    a_total = sum(v["a"] for v in batch3_stats.values())
    b_total = sum(v["b"] for v in batch3_stats.values())
    towns = sorted(batch3_stats.keys())
    lines = [
        "Google/Serper verify batch 3 — 2026-11-01",
        f"Towns in serper state at completion: {len(state.get('towns') or {})}",
        f"New towns verified this batch: {len(towns)}",
        "",
        "Summary",
        f"  A-grade added this batch: {a_total}",
        f"  B-grade held rows this batch: {b_total}",
        f"  Total A in google_a_items.json: {len(a_items)}",
        f"  Total held_google.json rows: {len(held)}",
        "",
        "Per town (A / B held this batch):",
    ]
    for t in towns:
        v = batch3_stats[t]
        lines.append(f"  {t}: {v['a']} / {v['b']}")
    lines.extend(
        [
            "",
            "Notes",
            "  Strict operator-site rule; verbatim phone+postcode required for A.",
            "  Loop stopped when Serper log shows Finished batch or all all_towns.txt appear in google_log.md Googled.",
        ]
    )
    BATCH3.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote", BATCH3)


if __name__ == "__main__":
    raise SystemExit(main())
