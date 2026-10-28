# Handoff #209 batch-1-map (28 Oct, ~06:25 GMT)

## Done
- 53aaf109a: merged fix/phone-qa-28oct (B1/B2/B4/B6/B7); hashes + sw tag recomputed (/workspace/rehash209.py).
- 3ad83a298: Motion round 3 (F1 FB logo removed, F3, M1, M2 44px close, M3 light mode); tests/test_motion_28oct_3.py.
- origin/main fda5abbc6 already contained (merge = up to date at 06:0x).
- WIP commit (untested): boot watchdog no longer reloads (&hmboot) when the URL already has hmheal=1/hmboot=1 or an old-cache heal is busy (no double reload on slow boot); static assert in test_iphone_freeze.py; test_iphone_journeys v90 case now waits for the v90 worker to be `activated` (no installing/waiting) before continuing.

## Not done
- Full suite NOT green/verified: last local run (-n 8, interrupted) showed ~40 F, unknown which; many may be box env (tiles/rebase_race). Re-run: `pytest -q tests -rf --tb=line`, then iPhone WebKit set from tests.yml iphone-webkit job, backup off and on, with HELPMAP_REAL_TILES=1.
- Review follow-up "test URL check rejects &heal=1": not located in this branch's tests (searched for heal=1 / URL checks); find and allow it without loosening other checks.
- Re-check rehash after index.html edit (rehash209.py ran; confirm test_sw_tag_hash passes).
- F2 Heston Farm -> Dean review list (no code).
- Do NOT merge/deploy; Grok Bot puts live after Grok Bot 2 PASS.
