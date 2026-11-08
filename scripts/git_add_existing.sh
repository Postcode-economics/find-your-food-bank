#!/usr/bin/env bash
# git add for the refresh workflows' publish lists. Plain 'git add a b c' stages nothing when one listed path is
# neither on disk nor tracked ("pathspec did not match"), so one missing log aborted the whole commit step.
# A path that is on disk or tracked is staged (a tracked file deleted on disk stages its removal);
# anything else is skipped with a warning.
set -u
keep=()
for p in "$@"; do
  if git check-ignore -q -- "$p"; then
    echo "::warning::ignored by .gitignore, so not staged: $p"
    continue
  fi
  if [ -e "$p" ] || git ls-files --error-unmatch -- "$p" >/dev/null 2>&1; then
    keep+=("$p")
  else
    echo "::warning::not on disk and not tracked, so not staged: $p"
  fi
done

# Speed item 4: if fetch_timing_shelters.json exists in logs/, stage it
if git check-ignore -q -- "logs/fetch_timing_shelters.json"; then
  :  # keep private
elif [ -e "logs/fetch_timing_shelters.json" ] || git ls-files --error-unmatch -- "logs/fetch_timing_shelters.json" >/dev/null 2>&1; then
  # Only add if not already in keep
  already=0
  for k in "${keep[@]}"; do
    if [ "$k" = "logs/fetch_timing_shelters.json" ]; then already=1; break; fi
  done
  if [ "$already" -eq 0 ]; then
    keep+=("logs/fetch_timing_shelters.json")
  fi
fi
[ ${#keep[@]} -eq 0 ] || git add -- "${keep[@]}"
