#!/usr/bin/env bash
# Run scripts/tailscale_policy_sync.py on CT108 (the only host that can read the vault OAuth client).
#
#   scripts/tailscale-policy-ct108.sh <check|export|plan|apply|drift> [tool args...]
#
# The tool and config/tailscale/ are streamed to a throw-away directory on CT108 (nothing is left behind), so CT108
# needs no checkout of this repo. Plan/rollback state persists in /var/lib/tailscale-policy-sync on CT108
# (override with TS_POLICY_STATE_DIR). `apply` is confirmed here, on the operator's terminal, because the remote
# stdin carries the file stream.
set -euo pipefail

cmd="${1:?usage: $0 <check|export|plan|apply|drift> [args...]}"
shift
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bastion="${TS_POLICY_BASTION:-0docker_bastion}"
state_dir="${TS_POLICY_STATE_DIR:-/var/lib/tailscale-policy-sync}"

if [[ "$cmd" == "apply" ]]; then
  read -r -p "Apply config/tailscale/policy.hujson to the LIVE tailnet policy? Type 'apply': " answer
  [[ "$answer" == "apply" ]] || { echo "aborted" >&2; exit 1; }
  set -- --yes "$@"
fi

paths=(scripts/tailscale_policy_sync.py)
[[ -d "$repo/config/tailscale" ]] && paths+=(config/tailscale)

quoted=""
for a in "$cmd" "$@"; do quoted+=" $(printf '%q' "$a")"; done
remote="set -euo pipefail; d=\$(mktemp -d); trap 'rm -rf \"\$d\"' EXIT; tar -x -C \"\$d\"; cd \"\$d\"; TS_POLICY_STATE_DIR=$(printf '%q' "$state_dir") python3 scripts/tailscale_policy_sync.py$quoted"

tar --no-xattrs --no-mac-metadata -C "$repo" -cf - "${paths[@]}" | ssh -o BatchMode=yes -o ConnectTimeout=20 "$bastion" \
  "pct exec 108 -- bash -c $(printf '%q' "$remote")"
