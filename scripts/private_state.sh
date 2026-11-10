#!/usr/bin/env bash
# Private run state (rule 97, Dean 8 Nov 2026). logs/ and reports/ are internal, so .gitignore keeps them out of this
# public repo. Since then every run started with no memory (learning back-off, two-run times confirmations, undo log,
# carry-forward dates, discovery caches). This script keeps that state in the PRIVATE repo helpmap-research-backup
# under site-run-state/, never in this repo, never as a workflow artifact, and never printed to the log.
#   restore        copy the saved logs/ and reports/ into this checkout (files already in the checkout win; merge rules in
#                  scripts/private_state_restore.py). Only when real saved state came back does it set
#                  HELPMAP_STATE_RESTORED=1; otherwise times auto-apply stays off for this run (scripts/auto_rules.py state_ok)
#   save <label>   main only: copy the files this run created or changed into site-run-state/<label>/ (one folder per
#                  layer: foodbanks, shelters, warmspaces, sweep, so parallel runs never write the same path), then commit
#                  and push privately; a refused push is retried on a fresh copy of the newest private repo
# Needs the Actions secret HELPMAP_STATE_KEY (a deploy key with write access on helpmap-research-backup only).
# With no key it does nothing and says so: the run carries on exactly as it does without saved state. Fail-safe:
# a clone or push problem is a warning, never a failed refresh.
set -u
mode="${1:-}"; label="${2:-run}"
case "$label" in foodbanks|shelters|warmspaces|sweep|run) ;; *) echo "private state: unknown layer label" >&2; exit 2 ;; esac
REPO="${PRIVATE_STATE_REPO:-git@github.com:Postcode-economics/helpmap-research-backup.git}"
DIR="site-run-state"
WORK="${PRIVATE_STATE_WORK:-${RUNNER_TEMP:-/tmp}/private-state}"
MARK="$WORK.restored"
KEY="${HELPMAP_STATE_KEY:-}"
say() { echo "private state: $*"; }
warn() { echo "::warning::private state: $*"; }

if [ -z "$KEY" ]; then
  say "no HELPMAP_STATE_KEY secret set, so nothing is $( [ "$mode" = save ] && echo saved || echo restored ) (this run has no saved state)"
  exit 0
fi

setup_ssh() {
  case "$REPO" in
    /*|file://*) return 0 ;;   # local test repo, no ssh
  esac
  local kd; kd="$(mktemp -d)"
  ( umask 077; printf '%s\n' "$KEY" > "$kd/key" )
  export GIT_SSH_COMMAND="ssh -i $kd/key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$kd/known_hosts"
}

fetch() {
  rm -rf "$WORK"
  git clone --quiet --depth 1 --filter=blob:none --sparse "$REPO" "$WORK" >/dev/null 2>&1 || return 1
  git -C "$WORK" sparse-checkout set "$DIR" >/dev/null 2>&1 || return 1
}

hashes() {  # "<sha256>  <path>" for every file under logs/ and reports/ of the given root
  ( cd "$1" && find logs reports -type f 2>/dev/null | LC_ALL=C sort | while read -r f; do sha256sum "$f"; done )
}

case "$mode" in
  restore)
    setup_ssh
    if ! fetch; then
      warn "could not read the private repo; starting without saved state, so times auto-apply is off for this run"
      : > "$MARK"; exit 0
    fi
    read -r n state < <(python3 "$(dirname "$0")/private_state_restore.py" "$WORK/$DIR" . 2>/dev/null || echo "0 missing")
    hashes . > "$MARK"
    if [ "$state" = present ]; then
      [ -n "${GITHUB_ENV:-}" ] && echo "HELPMAP_STATE_RESTORED=1" >> "$GITHUB_ENV"
      say "restored $n file(s) into logs/ and reports/"
    else
      warn "no saved state in the private repo ($n file(s) restored); times auto-apply is off for this run"
    fi
    ;;
  save)
    if [ "${GITHUB_REF:-refs/heads/main}" != "refs/heads/main" ]; then say "not main, nothing saved"; exit 0; fi
    setup_ssh
    [ -f "$MARK" ] || : > "$MARK"
    changed=$(hashes . | LC_ALL=C sort | comm -23 - <(LC_ALL=C sort "$MARK") | awk '{print $2}')
    if [ -z "$changed" ]; then say "no changed state files"; exit 0; fi
    for n in 1 2 3; do
      if ! fetch; then warn "could not read the private repo (try $n)"; sleep $((n * ${PRIVATE_STATE_RETRY_WAIT:-10})); continue; fi
      k=0
      while IFS= read -r rel; do
        [ -f "$rel" ] || continue
        if [ "$(stat -c %s "$rel")" -gt 50000000 ]; then warn "skipped a file over 50 MB"; continue; fi
        mkdir -p "$WORK/$DIR/$label/$(dirname "$rel")"; cp -p "$rel" "$WORK/$DIR/$label/$rel"; k=$((k + 1))
      done <<< "$changed"
      git -C "$WORK" add -A "$DIR" >/dev/null 2>&1
      if git -C "$WORK" diff --cached --quiet; then say "no changed state files"; exit 0; fi
      date +%s > "$WORK/$DIR/$label/.saved_at"; git -C "$WORK" add -A "$DIR" >/dev/null 2>&1
      git -C "$WORK" -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
        commit --quiet -m "Run state: $label ${GITHUB_RUN_ID:-}" >/dev/null 2>&1
      if git -C "$WORK" push --quiet origin HEAD >/dev/null 2>&1; then say "saved $k file(s)"; exit 0; fi
      warn "push refused (try $n), retrying on the newest copy"; sleep $((n * ${PRIVATE_STATE_RETRY_WAIT:-10}))
    done
    warn "state not saved this run"
    ;;
  *) echo "usage: private_state.sh restore | save <label>" >&2; exit 2 ;;
esac
exit 0
