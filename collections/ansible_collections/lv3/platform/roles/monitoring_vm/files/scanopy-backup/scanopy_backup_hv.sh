#!/usr/bin/env bash
# scanopy_backup_hv - hypervisor side of the Scanopy database backup (SSH forced command on the 0docker hypervisor).
#
# Installed as /usr/local/sbin/scanopy-backup-hv and bound to one dedicated key in root's authorized_keys:
#   command="/usr/local/sbin/scanopy-backup-hv",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding,from="<monitoring egress>" ssh-ed25519 AAAA... scanopy-backup
# The only thing the key can do is stream a gzip-compressed plain-SQL dump of the Scanopy database to stdout. The dump holds
# credential material (API key hashes, integration credentials): it is only ever written to the monitoring VM, mode 0600.
set -euo pipefail
case "${SSH_ORIGINAL_COMMAND:-dump}" in
  dump) ;;
  *) echo "refused: unknown command" >&2; exit 2 ;;
esac
docker exec scanopy-postgres-1 sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists' | gzip -9
