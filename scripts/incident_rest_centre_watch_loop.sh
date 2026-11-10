#!/usr/bin/env bash
# Repeat the incident rest centre watch every 10 minutes until near GitHub's 6-hour
# job limit. The workflow then requests the next run. The */10 cron is only a backup
# for when this chain has stopped. Publishes the same files as the one-shot job, and
# only when they changed. One alert issue if a check errors; the next good check closes it.
set -uo pipefail

if [ -z "${INCIDENT_WATCH_REEXEC:-}" ]; then
  # A later fast-forward replaces this file on disk. Bash would then read the new copy
  # mid-loop, so run from a private copy that git will not touch.
  export INCIDENT_WATCH_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  copy="${RUNNER_TEMP:-/tmp}/incident-rest-centre-watch-loop.$$.sh"
  cp "$0" "$copy"
  export INCIDENT_WATCH_REEXEC=1
  export INCIDENT_WATCH_COPY="$copy"
  exec bash "$copy"
fi

cd "${INCIDENT_WATCH_ROOT}"
trap 'rm -f "${INCIDENT_WATCH_COPY:-}"' EXIT

interval="${INCIDENT_WATCH_INTERVAL_S:-}"
budget="${INCIDENT_WATCH_BUDGET_S:-}"
if [ -z "$interval" ]; then interval=$(python scripts/incident_rest_centre_schedule.py interval) || exit 1; fi
if [ -z "$budget" ]; then budget=$(python scripts/incident_rest_centre_schedule.py budget) || exit 1; fi

stamp="${INCIDENT_WATCH_STAMP:-${RUNNER_TEMP:-/tmp}/incident-watch-start}"
mkdir -p "$(dirname "$stamp")"
log="${INCIDENT_WATCH_LOG:-}"

# Same publish list as before. Nothing else (not the site, not other layers).
publish_paths=(
  incident_rest_centre_live.json
  incident_rest_centre_live.js
  logs/incident_rest_centre_live_state.json
  logs/incident_rest_centre_switch_state.json
  logs/incident_rest_centre_pages.json
  reports/pending_dean.md
)

in_rebase() { [ -d "$(git rev-parse --git-path rebase-merge)" ] || [ -d "$(git rev-parse --git-path rebase-apply)" ]; }

# Behind or equal: fast-forward so this check sees the latest live file. Ahead: keep the
# unpushed commit. Diverged: rebase onto origin, with the same conflict helper as the push.
# Never reset away a commit that has not been pushed.
sync_tree() {
  ref="${GITHUB_REF_NAME:-}"
  [ -n "$ref" ] || return 0
  if [ -n "$(git status --porcelain)" ]; then
    echo "::warning::working tree not clean; skipping update before this check"
    return 0
  fi
  git fetch origin "$ref" || { echo "::warning::could not fetch origin/$ref"; return 0; }
  if git merge-base --is-ancestor HEAD "origin/$ref"; then
    git merge --ff-only "origin/$ref" || echo "::warning::fast-forward onto origin/$ref failed"
    return 0
  fi
  if git merge-base --is-ancestor "origin/$ref" HEAD; then
    return 0
  fi
  if git rebase "origin/$ref"; then return 0; fi
  if in_rebase && bash scripts/refresh_rebase_conflicts.sh && GIT_EDITOR=true git rebase --continue && ! in_rebase; then
    return 0
  fi
  git rebase --abort 2>/dev/null || true
  echo "::warning::could not rebase onto origin/$ref before this check"
}

push_with_retry() {
  local n
  for n in 1 2 3; do
    if git pull --rebase --autostash && git push; then return 0; fi
    if in_rebase && { bash scripts/refresh_rebase_conflicts.sh; GIT_EDITOR=true git rebase --continue; } && git push; then return 0; fi
    git rebase --abort 2>/dev/null || true
    sleep $((n * 5))
  done
  echo "::error::incident rest centre watch could not be pushed"
  return 1
}

# New place email (fail-safe): only after a check publishes, never fails the loop.
send_new_place_email() {
  [ -n "${1:-}" ] || return 0
  python scripts/new_live_email.py --layers emergency --baseline "$1" --send || echo "::warning::new place email failed"
}

publish() {
  local baseline
  baseline=$(git rev-parse "origin/${GITHUB_REF_NAME:-HEAD}" 2>/dev/null || git rev-parse HEAD)
  bash scripts/git_add_existing.sh "${publish_paths[@]}"
  committed=0
  if ! git diff --cached --quiet; then
    git config user.name "github-actions[bot]"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git commit -m "Incident rest centre watch $(date -u +%F-%H%M)" || return 1
    committed=1
  fi
  ref="${GITHUB_REF_NAME:-}"
  if [ -n "$ref" ] && git rev-parse --verify --quiet "origin/$ref" >/dev/null; then
    # Equal to origin: nothing to publish. Ahead: this commit, or one whose push failed.
    if git merge-base --is-ancestor HEAD "origin/$ref"; then
      echo "No change"
      return 0
    fi
  elif [ "$committed" -eq 0 ]; then
    echo "No change"
    return 0
  else
    echo "::error::no origin/$ref to push the incident rest centre watch commit to"
    return 1
  fi
  push_with_retry || return 1
  send_new_place_email "$baseline"
  return 0
}

# Rebuild gitignored state from the public live file when Actions cache left nothing
# (rule 97: logs/ stay out of the public repo).
python scripts/incident_rest_centre_live.py --hydrate-from-live || true

echo "Incident rest centre watch loop: every ${interval}s for up to ${budget}s"
job_start=$SECONDS
runs=0
last=0
while true; do
  runs=$((runs + 1))
  date +%s > "$stamp"
  iter_start=$SECONDS
  if [ "${INCIDENT_WATCH_STUB:-}" = 1 ]; then
    [ -n "$log" ] && echo "watch" >> "$log"
    code=0
  else
    sync_tree
    python scripts/incident_rest_centre_watch.py
    code=$?
    if [ "$code" -eq 0 ]; then
      publish
      code=$?
    fi
    if [ "$code" -ne 0 ]; then
      echo "::error::Incident rest centre watch failed"
      python scripts/alert.py open incident-watch "Incident rest centre watch failed" "The 10-minute rest centre (council-run) watch did not finish. Open the run log. A later successful run closes this issue." || echo "::error::incident rest centre watch alert could not be raised"
    else
      python scripts/alert.py resolve incident-watch || code=$?
    fi
  fi
  last=$code
  echo "incident rest centre watch: check ${runs} finished with exit ${code} at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    echo "- check ${runs} at $(date -u +%H:%M) UTC, exit ${code}" >> "$GITHUB_STEP_SUMMARY"
  fi
  if [ -n "${INCIDENT_WATCH_MAX_RUNS:-}" ] && [ "$runs" -ge "$INCIDENT_WATCH_MAX_RUNS" ]; then
    break
  fi
  elapsed=$((SECONDS - job_start))
  answer=$(python scripts/incident_rest_centre_schedule.py continue "$elapsed" "$budget" "$interval") || exit 1
  if [ "$answer" != yes ]; then
    break
  fi
  used=$((SECONDS - iter_start))
  nap=$((interval - used))
  if [ "$nap" -lt 1 ]; then nap=1; fi
  if [ "${INCIDENT_WATCH_SKIP_SLEEP:-}" != 1 ]; then
    sleep "$nap"
  fi
done
echo "Incident rest centre watch loop: ${runs} checks, handing back to the workflow"
exit "$last"
