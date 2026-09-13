#!/usr/bin/env bash
# Rendered by the private control repository. Never deletes disks, backups,
# containers, or application data.
set -Eeuo pipefail
exec 9>/run/lock/${RECOVERY_PREFIX:-proxmox}-storage-recovery.lock
flock -n 9 || exit 0

: "${RECOVERY_PREFIX:?}" "${NTFY_URL:?}" "${NTFY_USERNAME:?}" "${NTFY_PASSWORD_FILE:?}"
STATE_DIR=${STATE_DIR:-/var/lib/${RECOVERY_PREFIX}-host-control}
STATE_FILE="$STATE_DIR/storage-recovery.json"
MARKER="$STATE_DIR/ntfy-recovery-active"
mkdir -p "$STATE_DIR"

stats() { read -r total_kb free_kb < <(df -Pk / | awk 'NR==2 {print $2, $4}'); free_pct=$((free_kb * 100 / total_kb)); }
stats
cleanup=0; trimmed=(); resumed=()
if (( free_kb < 100 * 1024 * 1024 || free_pct < 15 )); then
  cleanup=1
  journalctl --vacuum-size=200M || true
  apt-get clean || true
  for vmid in $(qm list | awk 'NR>1 {print $1}'); do
    if timeout 90 qm guest exec "$vmid" -- fstrim -av >/dev/null 2>&1; then trimmed+=("$vmid"); fi
  done
  stats
fi

if (( free_kb >= 50 * 1024 * 1024 && free_pct >= 5 )) && pvesm status --storage local | awk 'NR>1 && $3 == "active" {ok=1} END {exit !ok}'; then
  while read -r vmid; do
    [[ "$(qm status "$vmid" 2>/dev/null | awk '/^status:/ {print $2}')" == io-error ]] || continue
    qm resume "$vmid" && resumed+=("$vmid") || logger -t "$RECOVERY_PREFIX-storage-recovery" "failed to resume VM $vmid"
  done < <(qm list | awk 'NR>1 {print $1}')
fi

printf '{"timestamp":"%s","root_free_kb":%s,"root_free_percent":%s,"cleanup":%s,"trimmed_vms":"%s","resumed_vms":"%s"}\n' "$(date -u +%FT%TZ)" "$free_kb" "$free_pct" "$cleanup" "${trimmed[*]:-}" "${resumed[*]:-}" > "$STATE_FILE.tmp"
mv "$STATE_FILE.tmp" "$STATE_FILE"

if (( cleanup == 0 && ${#resumed[@]} == 0 )); then rm -f "$MARKER"; fi
if [[ ! -e "$MARKER" ]] && (( cleanup == 1 || ${#resumed[@]} > 0 )); then
  if curl --connect-timeout 10 --max-time 20 --fail --silent --show-error \
    --user "$NTFY_USERNAME:$(<"$NTFY_PASSWORD_FILE")" \
    -H 'Title: Proxmox storage recovery action' -H 'Priority: 4' -H 'Tags: warning,floppy_disk' \
    -d "host=$(hostname -f) free_percent=$free_pct cleanup=$cleanup trimmed=${trimmed[*]:-none} resumed=${resumed[*]:-none}" "$NTFY_URL" >/dev/null; then
    touch "$MARKER"
  else logger -t "$RECOVERY_PREFIX-storage-recovery" 'ntfy publish failed'; fi
fi
logger -t "$RECOVERY_PREFIX-storage-recovery" "root_free=${free_pct}% cleanup=$cleanup trimmed=${trimmed[*]:-none} resumed=${resumed[*]:-none}"
