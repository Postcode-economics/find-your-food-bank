#!/bin/bash
# Resolve conflicts after `git pull --rebase` in a refresh or sweep.
# stamp.js keeps the later date of each layer. Generated pages keep MAIN's copy and
# are rebuilt by build_seo.py + seo_meta.py right after, so a run that started before
# a PR merged can never revert it. Sectioned reports merge per section. Other data
# files keep this run's copy. See scripts/rebase_resolve.py.
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/rebase_resolve.py
