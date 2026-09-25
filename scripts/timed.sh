#!/usr/bin/env bash
# =============================================================================
# scripts/timed.sh — instrumentation wrapper for bootstrap / converge steps
# =============================================================================
# Records each invocation's wall-clock + exit code to a JSON-lines journal so
# we can build a time-budget baseline over many runs. Works for any command
# (ssh, make, ansible-playbook, docker, etc.) — the first argument is just a
# human label used in the log filename and journal row.
#
# Usage:
#   scripts/timed.sh <step-label> <command...>
#
# Examples:
#   scripts/timed.sh bootstrap make bootstrap
#   scripts/timed.sh pve-repo-install ssh 0fork-jump 'apt-get install -y proxmox-ve'
#
# Journal:   <TIMING_DIR>/journal.ndjson    (1 line per step, JSON)
# Per-step:  <TIMING_DIR>/<UTC-ts>-<label>.log  (stdout+stderr)
#
# TIMING_DIR defaults to .local/timings/ under the repo root. Override via env:
#   TIMING_DIR=/tmp/mytimings scripts/timed.sh ...
#
# ADR 0437 — overlay-aware bootstrap. See docs/adr/0437-*.
# =============================================================================
set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TIMING_DIR="${TIMING_DIR:-${REPO_ROOT}/.local/timings}"
mkdir -p "$TIMING_DIR"
JOURNAL="${TIMING_DIR}/journal.ndjson"

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <step-label> <command...>" >&2
  exit 2
fi

LABEL="$1"; shift
TS=$(date -u +%Y%m%dT%H%M%SZ)
# Sanitise label for filename use (replace anything non-alphanumeric/dash/underscore with -).
SAFE_LABEL=$(printf '%s' "$LABEL" | tr -c 'A-Za-z0-9_.-' '-')
LOG="${TIMING_DIR}/${TS}-${SAFE_LABEL}.log"
START_EPOCH=$(date -u +%s)

{
  echo "=== ${LABEL} @ ${TS} ==="
  echo "+ $*"
  echo "---"
} | tee "$LOG"

"$@" 2>&1 | tee -a "$LOG"
RC=${PIPESTATUS[0]}

END_EPOCH=$(date -u +%s)
DURATION=$((END_EPOCH - START_EPOCH))

# Emit a JSON line. Escape backslashes and double-quotes in the command string.
CMD_ESC=$(printf '%s' "$*" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
LOG_ESC=$(printf '%s' "$LOG" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
LABEL_ESC=$(printf '%s' "$LABEL" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
printf '{"ts":"%s","label":"%s","duration_s":%d,"rc":%d,"cmd":"%s","log":"%s"}\n' \
  "$TS" "$LABEL_ESC" "$DURATION" "$RC" "$CMD_ESC" "$LOG_ESC" >> "$JOURNAL"

printf '\n[timing] %s: %ds, rc=%d, log=%s\n' "$LABEL" "$DURATION" "$RC" "$LOG"
exit $RC
