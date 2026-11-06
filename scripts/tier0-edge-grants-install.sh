#!/usr/bin/env bash
# Install (or check) the tier0-edge-grants job on CT108 (the builder) from this checkout.
#
#   scripts/tier0-edge-grants-install.sh            install the job, its grant builder, the wrapper and the units from origin/main (PAUSE, the state and the timer's enablement are untouched)
#   scripts/tier0-edge-grants-install.sh --check    compare everything the job runs with origin/main (read-only); exit 1 when anything differs
#
# The job runs ONLY installed copies and refuses to run when one of them differs from main, so a merge never executes by itself (docs/runbooks/standby-edge-grants.md). This script therefore installs
# files IDENTICAL to origin/main: reviewed, merged code, never a working tree or a branch. The tools the job shares with the tailnet policy reconciler (tailscale_policy_sync.py,
# tailscale_policy_reconcile.py, lockout-guard.json) are installed by scripts/tailscale-policy-reconcile-install.sh; --check covers them too and the install says when they are behind.
# Replaced files are kept in /root/tier0-script-backups/ (never next to the scripts they replaced). No secret is read, written or printed.
set -euo pipefail

mode="install"
case "${1:-}" in
  "") ;;
  --check) mode="check" ;;
  *) echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
host="${TIER0_GRANTS_HOST:-0docker_builder}"
files=(scripts/standby_edge_grants_job.py scripts/standby_edge_grants.py scripts/tailscale_policy_sync.py scripts/tailscale_policy_reconcile.py config/tailscale/lockout-guard.json
       config/ct108/tier0-edge-grants/tier0-edge-grants.sh config/ct108/tier0-edge-grants/tier0-edge-grants.service config/ct108/tier0-edge-grants/tier0-edge-grants.timer)

git -C "$repo" fetch --quiet origin main
if ! git -C "$repo" diff --quiet origin/main -- "${files[@]}" || [[ -n "$(git -C "$repo" status --porcelain -- "${files[@]}")" ]]; then
  echo "refusing: these files differ from origin/main (unmerged or uncommitted changes, or this checkout is behind): ${files[*]}" >&2
  echo "merge the change first, update this checkout to origin/main, then run this again." >&2
  exit 1
fi

remote='set -euo pipefail
d=$(mktemp -d); trap "rm -rf \"$d\"" EXIT; tar -x -C "$d"; cd "$d"
LIB=${T0_LIB:-/usr/local/lib/tier0-edge-grants}; TSLIB=${T0_TSLIB:-/usr/local/lib/tailscale-policy-sync}; BIN=${T0_BIN:-/usr/local/bin}; UNITS=${T0_UNITS:-/etc/systemd/system}
BACKUPS=${T0_BACKUPS:-/root/tier0-script-backups}; SYSTEMCTL=${T0_SYSTEMCTL:-systemctl}
# repo path | installed path | mode ("-" = shared with the reconciler: compared, never installed here)
pairs=("scripts/standby_edge_grants_job.py|$LIB/standby_edge_grants_job.py|0644" "scripts/standby_edge_grants.py|$LIB/standby_edge_grants.py|0644"
       "config/ct108/tier0-edge-grants/tier0-edge-grants.sh|$BIN/tier0-edge-grants.sh|0755"
       "config/ct108/tier0-edge-grants/tier0-edge-grants.service|$UNITS/tier0-edge-grants.service|0644" "config/ct108/tier0-edge-grants/tier0-edge-grants.timer|$UNITS/tier0-edge-grants.timer|0644"
       "scripts/tailscale_policy_sync.py|$TSLIB/tailscale_policy_sync.py|-" "scripts/tailscale_policy_reconcile.py|$TSLIB/tailscale_policy_reconcile.py|-" "config/tailscale/lockout-guard.json|$TSLIB/lockout-guard.json|-")
differ=0; shared_behind=0
[ "$MODE" = check ] || echo "before the install:"
for p in "${pairs[@]}"; do
  IFS="|" read -r src dst m <<< "$p"
  if [ ! -f "$dst" ]; then echo "MISSING  $dst"; differ=1; [ "$m" = "-" ] && shared_behind=1
  elif cmp -s "$src" "$dst"; then echo "same     $dst"
  else echo "DIFFERS  $dst"; differ=1; [ "$m" = "-" ] && shared_behind=1; fi
done
if [ "$MODE" = "check" ]; then
  [ "$differ" = 0 ] && echo "check: everything the job runs equals main" || echo "check: the job would refuse to run (installed files differ from main)"
  [ "$differ" = 0 ]; exit
fi
python3 -m py_compile scripts/standby_edge_grants_job.py scripts/standby_edge_grants.py
bash -n config/ct108/tier0-edge-grants/tier0-edge-grants.sh
python3 scripts/standby_edge_grants_job.py --help > /dev/null
ts=$(date -u +%Y%m%dT%H%M%SZ); bk="$BACKUPS/tier0-edge-grants-$ts"
for p in "${pairs[@]}"; do
  IFS="|" read -r src dst m <<< "$p"
  [ "$m" = "-" ] && continue
  if [ -f "$dst" ] && ! cmp -s "$src" "$dst"; then mkdir -p "$bk"; cp -p "$dst" "$bk/$(basename "$dst")"; fi
  install -d -m 0755 "$(dirname "$dst")"
  install -m "$m" "$src" "$dst"
done
"$SYSTEMCTL" daemon-reload
[ -d "$bk" ] && echo "replaced files kept in $bk"
echo "installed (sha256):"
for p in "${pairs[@]}"; do IFS="|" read -r src dst m <<< "$p"; [ "$m" = "-" ] || sha256sum "$dst"; done
[ "$shared_behind" = 0 ] || echo "NOTE: the reconciler tools in $TSLIB are not main yet (scripts/tailscale-policy-reconcile-install.sh): until they are, the job runs nothing"
echo "installed; PAUSE ($(ls /var/lib/tier0-edge-grants/PAUSE 2> /dev/null || echo "not set")) and the timer are as they were"'

envs=()
for v in T0_LIB T0_TSLIB T0_BIN T0_UNITS T0_BACKUPS T0_SYSTEMCTL; do
  if [ -n "${!v:-}" ]; then envs+=("$v=$(printf '%q' "${!v}")"); fi
done
tar_opts=(); if tar --version 2> /dev/null | grep -q bsdtar; then tar_opts=(--no-xattrs --no-mac-metadata); fi         # macOS: no extended attributes in the archive (GNU tar on the builder warns about them)
COPYFILE_DISABLE=1 tar ${tar_opts[@]+"${tar_opts[@]}"} -C "$repo" -cf - "${files[@]}" \
  | ssh -o BatchMode=yes -o ConnectTimeout=20 "$host" "env MODE=$mode ${envs[*]:-} bash -c $(printf '%q' "$remote")"
