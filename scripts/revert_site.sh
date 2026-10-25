#!/usr/bin/env bash
# Undo the SITE part of a commit (everything except .github/), so the bot never needs the `workflows` permission (25 Oct 2026).
# Files the commit added are removed; changed/deleted ones are restored from its parent. Usage: scripts/revert_site.sh <sha>
set -euo pipefail
sha="$1"
git diff --name-status --no-renames "$sha^" "$sha" | while IFS=$'\t' read -r st f; do
  case "$f" in .github/*) continue;; esac
  if [ "$st" = "A" ]; then git rm -q --ignore-unmatch -- "$f"; else git checkout "$sha^" -- "$f"; fi
done
if git diff --cached --quiet; then echo "nothing to revert outside .github/"; exit 0; fi
git commit -q -m "Auto-revert site files of ${sha:0:9} (live check failed; workflow files untouched)"
echo "reverted site files of $sha"
