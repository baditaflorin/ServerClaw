#!/usr/bin/env bash
# tier0-edge-grants (CT108, hourly): close the loop for the standby edge's tailnet grants. Takes a SPARSE, shallow, blob-less clone of the infrastructure repo (main: only the policy and the git copies of
# the six files named below, a few MB, not the whole tree) and runs the INSTALLED job (/usr/local/lib/tier0-edge-grants/standby_edge_grants_job.py) against it. The job runs nothing from the clone: it
# checks that every installed file it uses equals main, so a merge never executes by itself; scripts/tier0-edge-grants-install.sh installs a reviewed main. What the job does, its limits and the
# kill switches: docs/runbooks/standby-edge-grants.md.
#   tier0-edge-grants.sh              the real run (PR + merge when a pair that stays closed qualifies)
#   tier0-edge-grants.sh --dry-run    compute and validate everything, print the result, touch neither GitHub, the state nor the metrics
#   tier0-edge-grants.sh --rehearse   the whole PR flow for real (branch, PR, both CI contexts) but the PR is closed instead of merged; no state, no metrics, ignores PAUSE
# Config: TIER0_INFRA_REPO (baditaflorin/platform_server), TIER0_EDGE_GRANTS_STATE (/var/lib/tier0-edge-grants; `touch PAUSE` inside it stops the job), TIER0_EDGE_GRANTS_TEXTFILE,
# TIER0_EDGE_GRANTS_LIB (the installed job), TIER0_TS_LIB (the reconciler's installed tools).
# Exit: the job's: 0 nothing to do / waiting / merged / dry run, 3 could not run, 4 refused (a person looks), 5 the PR flow failed.
set -uo pipefail
umask 077
STATE=${TIER0_EDGE_GRANTS_STATE:-/var/lib/tier0-edge-grants}
TEXTFILE=${TIER0_EDGE_GRANTS_TEXTFILE:-/var/lib/prometheus-node-exporter/textfile/tier0_edge_grants.prom}
REPO=${TIER0_INFRA_REPO:-baditaflorin/platform_server}
LIB=${TIER0_EDGE_GRANTS_LIB:-/usr/local/lib/tier0-edge-grants}
TSLIB=${TIER0_TS_LIB:-/usr/local/lib/tailscale-policy-sync}
mkdir -p "$STATE"
exec 9> "$STATE/lock"
flock -n 9 || { echo "another tier0-edge-grants run is in progress"; exit 0; }
export GIT_TERMINAL_PROMPT=0

dry=0; for a in "$@"; do case "$a" in --dry-run | --rehearse) dry=1 ;; esac; done        # neither touches the metrics
could_not_run() {        # $1 = the reason. Only ok and the run time change: the numbers of the last good run stay readable
  echo "$1" >&2
  if [ "$dry" = 0 ]; then
    { echo "tier0_edge_grants_last_run_timestamp_seconds $(date +%s)"; echo "tier0_edge_grants_ok 0"
      grep -v -E '^tier0_edge_grants_(ok|last_run_timestamp_seconds) ' "$TEXTFILE" 2> /dev/null || true
    } > "$TEXTFILE.tmp" 2> /dev/null && chmod 0644 "$TEXTFILE.tmp" && mv -f "$TEXTFILE.tmp" "$TEXTFILE" || true
  fi
  echo "RESULT_JSON {\"status\": \"could not run\", \"could_not_run\": \"${1//\"/\'}\"}"
  exit 3
}

[ -f "$LIB/standby_edge_grants_job.py" ] || could_not_run "the job is not installed in $LIB (run scripts/tier0-edge-grants-install.sh from an up-to-date main)"
W=$(mktemp -d "${TIER0_TMPDIR:-/run}/tier0-edge-grants.XXXXXX") || W=""
{ [ -n "$W" ] && [ -d "$W" ]; } || could_not_run "cannot make a work directory under ${TIER0_TMPDIR:-/run}"         # never a clone into "/repo"
trap 'rm -rf "$W"' EXIT
FILES=(config/tailscale/policy.hujson config/tailscale/lockout-guard.json scripts/standby_edge_grants.py scripts/standby_edge_grants_job.py scripts/tailscale_policy_sync.py scripts/tailscale_policy_reconcile.py)
PATTERNS=(); for f in "${FILES[@]}"; do PATTERNS+=("/$f"); done
if ! gh repo clone "$REPO" "$W/repo" -- --depth 1 --filter=blob:none --sparse -q > /dev/null 2>&1; then
  could_not_run "cannot clone $REPO"
fi
git -C "$W/repo" sparse-checkout set --no-cone "${PATTERNS[@]}" > /dev/null 2>&1 || could_not_run "cannot check out the files of $REPO main"
for f in "${FILES[@]}"; do [ -f "$W/repo/$f" ] || could_not_run "$f is not in $REPO main"; done
python3 "$LIB/standby_edge_grants_job.py" --repo "$W/repo" --lib "$TSLIB" --slug "$REPO" --state "$STATE" --textfile "$TEXTFILE" "$@"
