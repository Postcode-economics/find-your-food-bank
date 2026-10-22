# helpmap.uk runbook (one page)

For Dean or a named back-up person. Everything below is done on github.com in the repository, or in the Cloudflare dashboard.

## Something looks wrong on the site
1. Check the Issues tab for an open `refresh-alert` issue: it names the run and the failing step.
2. Open Actions, pick the workflow, open the latest run and read the red step.
3. A single bad listing: add an override in `overrides/` (see README) or a line in the exclusion list, commit. It goes live in a minute or two.

## Pause the automatic refreshes
Actions → choose the workflow (`Refresh food bank data`, shelters, warm spaces, daily sweep) → `...` → **Disable workflow**. Re-enable the same way. The site keeps showing the last published data. The hourly watchdog will open a "no refresh for 10 hours" issue; close it when you re-enable.

## Put up a notice / take the site down
- Notice: edit `index.html` (e.g. a line above the footer), commit to `main`. Bump `?v=` on any changed JS/CSS and the cache name in `sw.js`, or returning visitors will keep the old copy.
- Emergency take-down: Settings → Pages → unpublish, or in Cloudflare add a rule that redirects helpmap.uk to a holding page.

## Push safely
Avoid pushing within ~10 minutes of a scheduled run (UTC 04:29/12:29/20:29 food banks, :41 shelters, :53 warm spaces, 01:00 sweep). Always `git pull --rebase` first; the bots own `data.js`, `access.js`, `shelters.js`, `warmspaces.js`, `stamp.js`, `logs/`, `reports/`.

## Hand over
The back-up person needs: GitHub access to the repository (collaborator), Cloudflare access to the helpmap.uk zone, access to the hello@helpmap.uk mailbox, and this file. Keep the credentials in a password manager with emergency access, not in the repository.

## Personal data incident
Follow `docs/BREACH.md`.
