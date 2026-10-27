# Map policy (rules 22 and 23)

Set by Dean Goff, 26 Oct 2026, 17:12 (UK time). Enforced by `tests/test_map_policy.py` and `tests/test_tile_fallback.py`.

## Rule 22: which map the site uses

1. **OpenStreetMap is the permanent default.** `tiles.js` lists it first and `tileCandidates()` always puts it first.
2. **OpenFreeMap is the automatic backup.** If OpenStreetMap tiles fail (401, 403, 429, or 4 failures in the last 20), the map switches to OpenFreeMap on its own.
   - Style: `https://tiles.openfreemap.org/styles/positron` (light). Never a dark style. The light map is kept in dark mode too.
   - Free, no key, no registration, no usage limit (openfreemap.org). Terms: https://openfreemap.org/tos/
   - Attribution shown on the map while it is active: **OpenFreeMap © OpenMapTiles Data from OpenStreetMap**.
   - Proven by `tests/test_tile_fallback.py::Browser::test_osm_blocked_switches_to_openfreemap_and_renders`, which aborts every OpenStreetMap request and checks that OpenFreeMap renders (non-blank) with its credit. It runs in CI before going live and against the live site in the `tile-fallback` job of `deploy-check.yml`.
3. **No Stadia Maps.**
4. **MapTiler is never the default.** It may only stay in `tiles.js` as a disabled future fallback with no key.

## Rule 23: bots and checks never use public tile servers

Tests, checks, monitors and bots (CI and the box) never load real tiles from OpenStreetMap, OpenFreeMap or any other public tile server. They use stubbed or blank tiles (`check_browser.stub_map_tiles`, the stub OpenFreeMap style in the tests) or an offline UK map.
