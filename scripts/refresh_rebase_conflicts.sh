#!/bin/bash
# Resolve conflicts after `git pull --rebase` in a refresh or sweep.
# stamp.js keeps the later date of each layer. A parallel refresh used to take the
# whole file (`git pull --rebase -X theirs`) and wipe the other layers' dates.
# Every other conflict keeps this run's file, as -X theirs did.
set -euo pipefail
cd "$(dirname "$0")/.."
for f in $(git diff --name-only --diff-filter=U); do
  if [ "$f" = stamp.js ]; then
    python scripts/stamp.py combine-index
    git add -- stamp.js
  elif git cat-file -e ":3:$f" 2>/dev/null; then
    git checkout --theirs -- "$f" && git add -- "$f"
  else
    git rm -q -- "$f"
  fi
done
