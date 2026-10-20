# Find your food bank (UK)

An interactive map of UK food banks and their donation/collection locations. Tap a pin for the address, phone number, a one-tap Google Maps route, and links to the food bank's own site. Times change, so always call ahead.

Built by Postcode Economics (Dean Goff), [@postcode_economics](https://www.instagram.com/postcode_economics/).

## Data source

Food bank data comes from [Give Food](https://www.givefood.org.uk/) via their public API (https://www.givefood.org.uk/api/). Give Food's terms ask that they are credited and told about projects built on their data; please check https://www.givefood.org.uk/api/ for the current terms. Postcodes are checked with [postcodes.io](https://postcodes.io). Map tiles © OpenStreetMap contributors.

## How it updates

A GitHub Action (`.github/workflows/refresh.yml`) runs nightly at 03:17 UTC (or on demand from the Actions tab). It runs `scripts/build.py`, which re-downloads the Give Food data, removes duplicates, applies the overrides below, and rewrites `data.js`. If the download fails or returns fewer than 80% of the current number of entries, it stops and leaves `data.js` unchanged. A changed `data.js` is committed, which republishes the GitHub Pages site.

## Overrides

Manual corrections live in `overrides/` and are re-applied on every refresh. Keys are the stable Give Food id shown in `data.js` as `id`:
- a food bank: its Give Food slug, e.g. `"example-foodbank"`
- a location: `"<foodbank-slug>/<location-slug>"`

`overrides/phones.json`:
```json
{ "example-foodbank": "01234 567890" }
```

`overrides/opening_times.json` (free text per entry, or structured if the page supports it):
```json
{ "example-foodbank": "Mon & Thu 10:00-12:00" }
```
