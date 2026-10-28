#!/usr/bin/env bash
# git add for the refresh workflows' publish lists. Plain 'git add a b c' stages nothing when one listed path is
# neither on disk nor tracked ("pathspec did not match"), so one missing log aborted the whole commit step.
# A path that is on disk or tracked is staged (a tracked file deleted on disk stages its removal);
# anything else is skipped with a warning.
set -u
keep=()
for p in "$@"; do
  if [ -e "$p" ] || git ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
    keep+=("$p")
  else
    echo "::warning::not on disk and not tracked, so not staged: $p"
  fi
done
[ ${#keep[@]} -eq 0 ] || git add -- "${keep[@]}"
