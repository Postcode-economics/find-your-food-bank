#!/usr/bin/env bash
# Rule 25 offline harness. One command for every coding agent.
# See scripts/offline_env/README.md.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
export OFFLINE_ROOT="$ROOT"
export PYTHONPATH="${ROOT}/scripts${PYTHONPATH:+:${PYTHONPATH}}"

if [[ "${1:-}" == "--self-check" ]]; then
  shift
  exec python3 "$ROOT/scripts/offline_env/harness.py" self-check "$@"
fi

PORT=0
HOST=127.0.0.1
ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="${2:?--port needs a value}"; shift 2 ;;
    --host) HOST="${2:?--host needs a value}"; shift 2 ;;
    --root) export OFFLINE_ROOT="${2:?--root needs a value}"; shift 2 ;;
    --) shift; ARGS+=("$@"); break ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

STATE=$(mktemp)
LOG=$(mktemp)
cleanup() {
  if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
  rm -f "$STATE" "$LOG"
}
trap cleanup EXIT

python3 "$ROOT/scripts/offline_env/harness.py" serve --host "$HOST" --port "$PORT" --root "$OFFLINE_ROOT" --state "$STATE" --log "$LOG" &
PID=$!

for _ in $(seq 1 200); do
  if [[ -s "$STATE" ]]; then
    break
  fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "offline harness: server failed to start" >&2
    exit 1
  fi
  sleep 0.05
done
if [[ ! -s "$STATE" ]]; then
  echo "offline harness: server did not report a port" >&2
  exit 1
fi

OFFLINE_BASE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["base"])' "$STATE")
OFFLINE_SNAPSHOT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot"])' "$STATE")
export OFFLINE_BASE OFFLINE_SNAPSHOT OFFLINE_LOG="$LOG"

if [[ ${#ARGS[@]} -eq 0 ]]; then
  echo "serving $OFFLINE_BASE  (Ctrl-C to stop)" >&2
  wait "$PID"
  exit $?
fi

set +e
"${ARGS[@]}"
code=$?
set -e
python3 "$ROOT/scripts/offline_env/harness.py" check-log --log "$LOG"
logcode=$?
if [[ "$code" -ne 0 ]]; then
  exit "$code"
fi
exit "$logcode"
