#!/usr/bin/env python3
"""Run Serper Google searches for UK towns (3 queries each). Key from SERPER_API_KEY env only."""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOWNS_FILE = os.environ.get("TOWNS_FILE", "")
LOG_MD = ROOT / "google_log.md"
RAW = ROOT / "logs" / "google_serper_raw.jsonl"
STATE = ROOT / "logs" / "google_serper_state.json"

QUERIES = (
    "{town} homeless hostel night shelter",
    "{town} homeless day centre",
    "{town} foyer young people homeless 16-25",
)

SKIP_HOST_PARTS = (
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "tiktok.com", "wikipedia.org", "yelp.", "tripadvisor.",
    "find-open.co.uk", "homeless.org.uk/find-help", "homelesslink.org.uk",
    "streetlink.org.uk", "bbc.co.uk", "theguardian.com", "itv.com",
    "google.com", "bing.com", "reddit.com", "trustpilot.",
)


def load_towns(path):
    towns = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if len(line) < 3 or line.endswith(")"):
            continue
        if ";" in line or line.startswith("minus ") or "compiled from" in line.lower():
            continue
        if line.startswith("YH:"):
            line = line.split(":", 1)[1].strip()
        towns.append(line)
    return towns


def parse_done(log_text):
    done = set()
    in_done = False
    for line in log_text.splitlines():
        if line.startswith("## Googled"):
            in_done = True
            continue
        if line.startswith("## ") and not line.startswith("## Googled"):
            if in_done:
                in_done = False
            continue
        if in_done and line.startswith("- "):
            done.add(line[2:].strip())
    return done


def serper_search(key, q):
    body = json.dumps({"q": q, "gl": "gb", "num": 10}).encode()
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=body,
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main():
    key = os.environ.get("SERPER_API_KEY", "").strip()
    if not key:
        print("SERPER_API_KEY not set", file=sys.stderr)
        return 1
    towns_path = TOWNS_FILE or str(ROOT / "data" / "all_towns.txt")
    if not Path(towns_path).exists():
        print("towns file missing:", towns_path, file=sys.stderr)
        return 1

    towns = load_towns(towns_path)
    log_text = LOG_MD.read_text(encoding="utf-8") if LOG_MD.exists() else ""
    done = parse_done(log_text)
    state = json.loads(STATE.read_text()) if STATE.exists() else {"credits_used": 0, "towns": {}}
    credits_used = int(state.get("credits_used", 0))

    RAW.parent.mkdir(parents=True, exist_ok=True)
    batch = os.environ.get("BATCH", "").strip()
    limit = int(os.environ.get("LIMIT", "0") or "0")

    pending = [t for t in towns if t not in done]
    if batch:
        pending = [t for t in pending if t.lower() <= batch.lower()]  # unused
    if limit:
        pending = pending[:limit]

    for town in pending:
        town_results = []
        for tpl in QUERIES:
            q = tpl.format(town=town)
            try:
                data = serper_search(key, q)
            except urllib.error.HTTPError as e:
                print(f"HTTP {e.code} for {town!r}: {q}", file=sys.stderr)
                if e.code == 402:
                    break
                time.sleep(2)
                continue
            credits_used += 1
            organic = data.get("organic") or []
            filtered = []
            for row in organic:
                link = (row.get("link") or "").strip()
                low = link.lower()
                if not link or any(p in low for p in SKIP_HOST_PARTS):
                    continue
                filtered.append(
                    {
                        "title": row.get("title"),
                        "link": link,
                        "snippet": row.get("snippet"),
                    }
                )
            town_results.append({"query": q, "organic": filtered})
            with RAW.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {"town": town, "query": q, "organic": filtered, "ts": time.time()},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            time.sleep(0.35)
        state["towns"][town] = town_results
        state["credits_used"] = credits_used
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        done.add(town)
        # append to log
        if LOG_MD.exists():
            text = LOG_MD.read_text(encoding="utf-8")
        else:
            text = "# Google search log (helpmap shelters)\n\n## Googled\n\n## Credits\n\n"
        if f"- {town}\n" not in text and f"- {town}\r\n" not in text:
            if "## Still to Google" in text:
                text = text.replace("## Still to Google", f"- {town}\n\n## Still to Google")
            elif "## Credits" in text:
                text = text.replace("## Credits", f"- {town}\n\n## Credits")
            else:
                text = text.rstrip() + f"\n- {town}\n"
        # update credits section
        rem = max(0, 2500 - credits_used)
        if "## Credits" in text:
            text = re.sub(
                r"## Credits\n.*?(?=\n## |\Z)",
                f"## Credits\n\n- Used (this run): {credits_used}\n- Estimated remaining: {rem}\n",
                text,
                flags=re.S,
            )
        else:
            text += f"\n## Credits\n\n- Used (this run): {credits_used}\n- Estimated remaining: {rem}\n"
        LOG_MD.write_text(text, encoding="utf-8")
        print(f"Done {town} ({credits_used} credits used)")

    print(f"Finished batch. credits_used={credits_used}, pending_left={len([t for t in towns if t not in done])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
