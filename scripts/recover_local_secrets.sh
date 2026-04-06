#!/usr/bin/env bash
# recover_local_secrets.sh — Pull deployed secrets from VMs back to .local/
#
# This script uses qm guest exec via the Proxmox host to read deployed
# credential files from /etc/lv3/ on each VM and write them into the
# repo's .local/ directory, mapping VM-side paths to the .local/ layout
# that Ansible inventory expects.
#
# Usage: bash scripts/recover_local_secrets.sh
#
# Prerequisites:
#   - SSH access to Proxmox host (10.10.10.1) as root
#   - QEMU Guest Agent running on target VMs

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_ROOT="$REPO_ROOT/.local"
PROXMOX_HOST="root@10.10.10.1"

log() { echo "[recover] $*"; }
warn() { echo "[recover] WARNING: $*" >&2; }

qm_read_file() {
    local vmid="$1" remote_path="$2"
    ssh -o ConnectTimeout=10 "$PROXMOX_HOST" \
        "qm guest exec $vmid -- cat '$remote_path'" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if d.get('exitcode', 1) != 0:
        sys.exit(1)
    data = d.get('out-data', '')
    sys.stdout.write(data)
except Exception:
    sys.exit(1)
"
}

write_secret() {
    local local_path="$1" content="$2"
    mkdir -p "$(dirname "$local_path")"
    printf '%s' "$content" > "$local_path"
    chmod 600 "$local_path"
}

recover_from_vm() {
    local vmid="$1" vm_name="$2"
    shift 2
    log "--- VM $vmid ($vm_name) ---"
    while [[ $# -gt 0 ]]; do
        local remote_path="$1" local_path="$2"
        shift 2
        local full_local="$LOCAL_ROOT/$local_path"
        if content=$(qm_read_file "$vmid" "$remote_path"); then
            write_secret "$full_local" "$content"
            log "  OK: $local_path"
        else
            warn "  SKIP: $remote_path (not found or unreadable)"
        fi
    done
}

# ── docker-runtime-lv3 (VMID 120) — hosts most services ──────────────
recover_from_vm 120 docker-runtime-lv3 \
    /etc/lv3/keycloak/bootstrap-admin-password       keycloak/bootstrap-admin-password.txt \
    /etc/lv3/keycloak/admin-client-secret             keycloak/admin-client-secret.txt \
    /etc/lv3/keycloak/florin.badita-password           keycloak/florin.badita-password.txt \
    /etc/lv3/keycloak/outline.automation-password      keycloak/outline.automation-password.txt \
    /etc/lv3/keycloak/recovery-admin-service-secret    keycloak/recovery-admin-service-secret.txt \
    /etc/lv3/gitea/admin-password                     gitea/admin-password.txt \
    /etc/lv3/gitea/admin-token                        gitea/admin-token.txt \
    /etc/lv3/gitea/webhook-secret                     gitea/webhook-secret.txt \
    /etc/lv3/gitea/renovate-password                  gitea/renovate-password.txt \
    /etc/lv3/gitea/renovate-token                     gitea/lv3-reconcile-read-token.txt \
    /etc/lv3/gitea/runner-registration-token           gitea/runner-registration-token.txt \
    /etc/lv3/dify/secret-key.txt                      dify/secret-key.txt \
    /etc/lv3/dify/admin-password.txt                  dify/admin-password.txt \
    /etc/lv3/dify/init-password.txt                   dify/init-password.txt \
    /etc/lv3/dify/plugin-daemon-key.txt               dify/plugin-daemon-key.txt \
    /etc/lv3/dify/plugin-inner-api-key.txt            dify/plugin-inner-api-key.txt \
    /etc/lv3/dify/qdrant-api-key.txt                  dify/qdrant-api-key.txt \
    /etc/lv3/dify/redis-password.txt                  dify/redis-password.txt \
    /etc/lv3/dify/sandbox-api-key.txt                 dify/sandbox-api-key.txt \
    /etc/lv3/dify/tools-api-key.txt                   dify/tools-api-key.txt \
    /etc/lv3/directus/admin-password.txt              directus/admin-password.txt \
    /etc/lv3/directus/key.txt                         directus/key.txt \
    /etc/lv3/directus/secret.txt                      directus/secret.txt \
    /etc/lv3/flagsmith/admin-password.txt             flagsmith/admin-password.txt \
    /etc/lv3/flagsmith/django-secret-key.txt          flagsmith/django-secret-key.txt \
    /etc/lv3/glitchtip/secret-key                     glitchtip/secret-key.txt \
    /etc/lv3/glitchtip/valkey-password                glitchtip/valkey-password.txt \
    /etc/lv3/grist/session-secret.txt                 grist/session-secret.txt \
    /etc/lv3/label-studio/admin-password.txt          label-studio/admin-password.txt \
    /etc/lv3/label-studio/admin-token.txt             label-studio/admin-token.txt \
    /etc/lv3/lago/bootstrap-user-password.txt         lago/bootstrap-user-password.txt \
    /etc/lv3/lago/encryption-deterministic-key.txt    lago/encryption-deterministic-key.txt \
    /etc/lv3/lago/encryption-key-derivation-salt.txt  lago/encryption-key-derivation-salt.txt \
    /etc/lv3/lago/encryption-primary-key.txt          lago/encryption-primary-key.txt \
    /etc/lv3/lago/org-api-key.txt                     lago/org-api-key.txt \
    /etc/lv3/lago/redis-password.txt                  lago/redis-password.txt \
    /etc/lv3/lago/rsa-private-key.pem                 lago/rsa-private-key.pem \
    /etc/lv3/lago/secret-key-base.txt                 lago/secret-key-base.txt \
    /etc/lv3/lago/smoke-producer-token.txt            lago/smoke-producer-token.txt \
    /etc/lv3/langfuse/bootstrap-user-password.txt     langfuse/bootstrap-user-password.txt \
    /etc/lv3/langfuse/clickhouse-password.txt         langfuse/clickhouse-password.txt \
    /etc/lv3/langfuse/encryption-key.txt              langfuse/encryption-key.txt \
    /etc/lv3/langfuse/minio-root-password.txt         langfuse/minio-secret-key.txt \
    /etc/lv3/langfuse/nextauth-secret.txt             langfuse/nextauth-secret.txt \
    /etc/lv3/langfuse/project-public-key.txt          langfuse/project-public-key.txt \
    /etc/lv3/langfuse/project-secret-key.txt          langfuse/project-secret-key.txt \
    /etc/lv3/langfuse/redis-password.txt              langfuse/redis-password.txt \
    /etc/lv3/langfuse/salt.txt                        langfuse/salt.txt \
    /etc/lv3/mail-platform/gateway-api-key            mail-platform/gateway-api-key.txt \
    /etc/lv3/mail-platform/metrics-password            mail-platform/metrics-password.txt \
    /etc/lv3/mail-platform/server-mailbox-password     mail-platform/server-mailbox-password.txt \
    /etc/lv3/mail-platform/stalwart-admin-password     mail-platform/stalwart-admin-password.txt \
    /etc/lv3/matrix-synapse/ops-password.txt          matrix-synapse/ops-password.txt \
    /etc/lv3/matrix-synapse/registration-shared-secret.txt matrix-synapse/registration-shared-secret.txt \
    /etc/lv3/mattermost/admin-password                mattermost/admin-password.txt \
    /etc/lv3/mattermost/incoming-webhooks.json        mattermost/incoming-webhooks.json \
    /etc/lv3/minio/root-password.txt                  minio/root-password.txt \
    /etc/lv3/monitoring/netdata-stream-api-key         monitoring/netdata-stream-api-key.txt \
    /etc/lv3/n8n/encryption-key.txt                   n8n/encryption-key.txt \
    /etc/lv3/n8n/owner-password.txt                   n8n/owner-password.txt \
    /etc/lv3/nextcloud/admin-password.txt             nextcloud/admin-password.txt \
    /etc/lv3/nextcloud/redis-password.txt             nextcloud/redis-password.txt \
    /etc/lv3/open-webui/admin-password.txt            open-webui/admin-password.txt \
    /etc/lv3/open-webui/webui-secret-key.txt          open-webui/webui-secret-key.txt \
    /etc/lv3/outline/secret-key.txt                   outline/secret-key.txt \
    /etc/lv3/outline/redis-password.txt               outline/redis-password.txt \
    /etc/lv3/outline/minio-root-password.txt          outline/minio-root-password.txt \
    /etc/lv3/outline/utils-secret.txt                 outline/utils-secret.txt \
    /etc/lv3/outline/production-api-key               outline/api-token.txt \
    /etc/lv3/paperless/admin-password.txt             paperless/admin-password.txt \
    /etc/lv3/paperless/secret-key.txt                 paperless/secret-key.txt \
    /etc/lv3/paperless/redis-password.txt             paperless/redis-password.txt \
    /etc/lv3/paperless/api-token                      paperless/api-token.txt \
    /etc/lv3/paperless/taxonomy.json                  paperless/taxonomy.json \
    /etc/lv3/plane/bootstrap-admin-password.txt       plane/bootstrap-admin-password.txt \
    /etc/lv3/plane/secret-key.txt                     plane/secret-key.txt \
    /etc/lv3/plane/rabbitmq-password.txt              plane/rabbitmq-password.txt \
    /etc/lv3/plane/aws-secret-access-key.txt          plane/aws-secret-access-key.txt \
    /etc/lv3/plane/live-server-secret-key.txt         plane/live-server-secret-key.txt \
    /etc/lv3/plausible/bootstrap-user-password.txt    plausible/bootstrap-user-password.txt \
    /etc/lv3/plausible/secret-key-base.txt            plausible/secret-key-base.txt \
    /etc/lv3/plausible/database-password.txt          plausible/database-password.txt \
    /etc/lv3/searxng/secret-key.txt                   searxng/secret-key.txt \
    /etc/lv3/semaphore/admin-password                 semaphore/admin-password.txt \
    /etc/lv3/superset/admin-password.txt              superset/admin-password.txt \
    /etc/lv3/superset/secret-key.txt                  superset/secret-key.txt \
    /etc/lv3/vikunja/api-token.txt                    vikunja/api-token.txt \
    /etc/lv3/vikunja/bootstrap-password.txt           vikunja/automation-password.txt \
    /etc/lv3/vikunja/service-secret.txt               vikunja/service-secret.txt \
    /etc/lv3/vikunja/webhook-secret.txt               vikunja/webhook-secret.txt \
    /etc/lv3/windmill/superadmin-secret               windmill/superadmin-secret.txt \
    /etc/lv3/woodpecker/agent-secret                  woodpecker/agent-secret.txt \
    /etc/lv3/harbor/admin-password                    harbor/admin-password.txt \
    /etc/lv3/harbor/database-password                 harbor/database-password.txt \
    /etc/lv3/netbox/secret-key                        netbox/secret-key.txt \
    /etc/lv3/jupyterhub/service-api-token.txt         jupyterhub/service-api-token.txt \
    /etc/lv3/jupyterhub/minio-root-password.txt       jupyterhub/minio-root-password.txt \
    /etc/lv3/platform-context/api-token.txt           platform-context/api-token.txt \
    /etc/lv3/ops-portal/session-secret.txt            ops-portal/oauth2-proxy-cookie-secret.txt \
    /etc/lv3/step-ca/hosts-password.txt               step-ca/secrets/provisioners/hosts-password.txt

# ── postgres-lv3 (VMID 150) — database passwords ─────────────────────
log ""
recover_from_vm 150 postgres-lv3 \
    /etc/lv3/postgres/keycloak-password.txt           keycloak/database-password.txt \
    /etc/lv3/postgres/dify-password.txt               dify/database-password.txt \
    /etc/lv3/postgres/directus-password.txt           directus/database-password.txt \
    /etc/lv3/postgres/flagsmith-password.txt           flagsmith/database-password.txt \
    /etc/lv3/postgres/gitea-password.txt               gitea/database-password.txt \
    /etc/lv3/postgres/glitchtip-password.txt           glitchtip/database-password.txt \
    /etc/lv3/postgres/label-studio-password.txt        label-studio/database-password.txt \
    /etc/lv3/postgres/lago-password.txt               lago/database-password.txt \
    /etc/lv3/postgres/langfuse-password.txt           langfuse/database-password.txt \
    /etc/lv3/postgres/matrix-synapse-password.txt     matrix-synapse/database-password.txt \
    /etc/lv3/postgres/mattermost-password.txt         mattermost/database-password.txt \
    /etc/lv3/postgres/n8n-password.txt                n8n/database-password.txt \
    /etc/lv3/postgres/netbox-password.txt             netbox/database-password.txt \
    /etc/lv3/postgres/nextcloud-password.txt          nextcloud/database-password.txt \
    /etc/lv3/postgres/one-api-password.txt            one-api/database-password.txt \
    /etc/lv3/postgres/openfga-password.txt            openfga/database-password.txt \
    /etc/lv3/postgres/outline-password.txt            outline/database-password.txt \
    /etc/lv3/postgres/paperless-password.txt          paperless/database-password.txt \
    /etc/lv3/postgres/plane-password.txt              plane/database-password.txt \
    /etc/lv3/postgres/plausible-password.txt          plausible/database-password.txt \
    /etc/lv3/postgres/semaphore-password.txt          semaphore/database-password.txt \
    /etc/lv3/postgres/superset-password.txt           superset/database-password.txt \
    /etc/lv3/postgres/temporal-password.txt           temporal/database-password.txt \
    /etc/lv3/postgres/vikunja-password.txt            vikunja/database-password.txt \
    /etc/lv3/postgres/vaultwarden-password.txt        vaultwarden/database-password.txt \
    /etc/lv3/postgres/windmill-password.txt           windmill/database-password.txt \
    /etc/lv3/postgres/woodpecker-password.txt         woodpecker/database-password.txt \
    /etc/lv3/postgres/sftpgo-password.txt             sftpgo/database-password.txt

# ── openbao on docker-runtime-lv3 ────────────────────────────────────
log ""
log "--- OpenBao secrets (VMID 120) ---"
recover_from_vm 120 docker-runtime-lv3-openbao \
    /etc/lv3/openbao/init.json                        openbao/init.json

# ── monitoring-lv3 (VMID 140) ────────────────────────────────────────
log ""
recover_from_vm 140 monitoring-lv3 \
    /etc/lv3/monitoring/netdata-stream-api-key         monitoring/netdata-stream-api-key.txt

# ── nginx-lv3 (VMID 110) — ntfy, headscale ───────────────────────────
log ""
recover_from_vm 110 nginx-lv3 \
    /etc/lv3/ntfy/alertmanager-password               ntfy/alertmanager-password.txt \
    /etc/lv3/headscale/api-key                        headscale/api-key.txt

# ── backup-lv3 (VMID 160) ────────────────────────────────────────────
log ""
recover_from_vm 160 backup-lv3 \
    /etc/lv3/proxmox-backup/backup-lv3-token.json     proxmox-backup/backup-lv3-token.json

log ""
log "Recovery complete. Review .local/ contents and test SSH access."
log "Recovered files:"
find "$LOCAL_ROOT" -type f | wc -l | xargs echo "  Total files:"
