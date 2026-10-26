# Offline harness (rule 25)

This is the standard way to run the site in tests. Every coding agent uses it. It never contacts the live site and it never fetches a map tile.

`scripts/offline_env/run.sh` is the one command. `scripts/offline_env/harness.py` is the Python helper tests import.

## What it covers

- A loopback static server for this checkout (the same job as `python -m http.server`).
- A snapshot, taken once at start, of `data.js`, `data.full.js` when it is present, `stamp.js`, and any other file in the repo root whose name contains `stamp`. Those URLs are served from the snapshot for the rest of the run. Editing the checkout copy afterwards does not change what the browser receives. Restart the harness to freeze a new copy. Every other file (HTML, CSS, JS) is read from the checkout, so edits show up on the next reload.
- Playwright routing for every tile host, answered with a 1×1 transparent PNG and `access-control-allow-origin: *`:
  - `tile.openstreetmap.org` and `*.tile.openstreetmap.org`
  - `openfreemap.org` and `*.openfreemap.org`
  - `api.maptiler.com`
  - `stadiamaps.com` and `*.stadiamaps.com` (including `tiles.stadiamaps.com`)
- Playwright routing for `helpmap.uk` and any `*.helpmap.uk` host (including `www`). The response is the local file, or the snapshot for `data.js` and the stamps. A missing file is a local 404. Nothing is fetched from the network.
- A request log. Any other `http`, `https`, `ws`, or `wss` host is an external request. It is printed, aborted, and fails the run. That includes `api.postcodes.io`, `formsubmit.co`, `static.cloudflareinsights.com`, Google Maps, and the MapTiler and OpenStreetMap websites (those are not tile hosts).
- `launch` and `offline_context`, the browser factory other tests import, plus a pytest fixture named `offline`.

The server binds to `127.0.0.1` only. It refuses proxy requests (`CONNECT`, an absolute URL, `POST`). Paths that escape the checkout are 404s.

## One command

From the repo root:

```bash
scripts/offline_env/run.sh
```

Serves until Ctrl-C and prints `OFFLINE_BASE` and `OFFLINE_SNAPSHOT`.

```bash
scripts/offline_env/run.sh -- python -m pytest -q tests
scripts/offline_env/run.sh -- python scripts/journeys.py
```

The command inherits:

| Variable | Meaning |
|---|---|
| `OFFLINE_BASE` | `http://127.0.0.1:<port>/` |
| `OFFLINE_SNAPSHOT` | Directory of the frozen `data.js` and stamps |
| `OFFLINE_LOG` | JSONL request log |
| `OFFLINE_ROOT` | Checkout being served |
| `PYTHONPATH` | `<repo>/scripts` prepended, so `import offline_env` works |

When the command exits, the log is checked. Exit status is the command's status, or 1 if the command passed and any external request was logged. A line looks like `OFFLINE external blocked: GET https://api.postcodes.io/...`.

```bash
scripts/offline_env/run.sh --self-check
```

Checks the snapshot server, the host classification, and (when Playwright and Chromium or Google Chrome are installed) a real page load of `https://helpmap.uk/?nocount` that must be answered locally. `--no-browser` skips that last part.

## Importing the fixture

The repo's browser tests are unittest-style. Put `scripts` on `PYTHONPATH` (the shell script does) and import the factory:

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from playwright.sync_api import sync_playwright
from offline_env import launch, offline_context

def test_cards():
    with sync_playwright() as pw:
        browser = launch(pw)
        routed = offline_context(browser, viewport={'width': 390, 'height': 844})
        try:
            page = routed.new_page()
            # https://helpmap.uk is served from this checkout. WebKit upgrades http
            # subresources (the page sends upgrade-insecure-requests), so use this
            # origin there. Chromium can also use routed.base, the loopback server.
            page.goto(routed.helpmap + '/?nocount', wait_until='domcontentloaded')
            page.wait_for_function('()=>window.FB_DATA&&FB_DATA.items.length>100')
            routed.assert_clean()
        finally:
            routed.close()  # also asserts the log is clean
        browser.close()
```

`offline_context` uses `scripts/check_browser.py` for the user agent (`helpmap-check`, so the analytics beacon stays off), the shared timeouts, and `service_workers='block'`. Pass `service_workers='allow'` only for a test that has to install a worker. Keyword arguments otherwise match `browser.new_context` (`viewport`, `color_scheme`, `geolocation`, `permissions`, …).

`launch` turns off Chrome's background update and telemetry switches. It uses Playwright's Chromium when that browser is installed, otherwise `/usr/bin/google-chrome`. Set `OFFLINE_CHROME` to force a binary. In a container it adds `--no-sandbox` (or set `OFFLINE_NO_SANDBOX=1`).

Under `run.sh`, `offline_context` attaches to the server that is already running. Called on its own, it starts one and stops it on `close`.

Pytest, when it is installed and the test module names the plugin:

```python
pytest_plugins = ['offline_env']

def test_list(offline):
    # offline.base, offline.helpmap, offline.snapshot, offline.assert_clean()
    ...
```

The fixture fails the test if the shared log contains an external request.

Register a narrower Playwright route **after** `offline_context` when a test must answer a host itself. The last route wins, so this response is local and is not an external failure:

```python
routed.context.route(
    'https://api.postcodes.io/**',
    lambda route: route.fulfill(
        status=200, content_type='application/json',
        body='{"status":200,"result":{"postcode":"BN17 5LF","latitude":50.8095,"longitude":-0.5405}}'))
```

County names are resolved from `counties.json` and do not need that stub. A postcode or town search that is left unstubbed calls `api.postcodes.io`, the harness blocks it, and the run fails even though the page then falls back to `outcodes.json`.

Do not `page.goto('https://helpmap.uk')` with a context this factory did not set up, and do not point a test at the live origin to "compare". Tile image checks should expect a 200 `image/png` from the stub, not a live tile.

## Rules that sit next to this

Work stays offline. Do not merge. This directory does not change the site. Feature work keeps the existing card design, dark mode, and Welsh copy, and uses the shared limits `window.SHOW_LIMITS = {first: 5, more: 10}` and `window.showMoreResults()` in `showmore.js`, with cards in `#list` as `.card` elements.
