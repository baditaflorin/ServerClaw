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

# ── SSH multiplexing: reuse a single TCP connection ──────────────────
SSH_CONTROL_DIR=$(mktemp -d)
SSH_OPTS="-o ControlMaster=auto -o ControlPath=$SSH_CONTROL_DIR/%r@%h:%p -o ControlPersist=120 -o ConnectTimeout=10"

cleanup() {
    ssh -O exit $SSH_OPTS "$PROXMOX_HOST" 2>/dev/null || true
    rm -rf "$SSH_CONTROL_DIR"
}
trap cleanup EXIT

# Warm up the control connection
ssh $SSH_OPTS "$PROXMOX_HOST" true 2>/dev/null

log() { echo "[recover] $*"; }
warn() { echo "[recover] WARNING: $*" >&2; }

# ── Batch recovery: one qm guest exec per VM, reads all files at once ─
recover_from_vm_batch() {
    local vmid="$1" vm_name="$2"
    shift 2

    local remote_paths=() local_paths=()
    while [[ $# -gt 0 ]]; do
        remote_paths+=("$1")
        local_paths+=("$2")
        shift 2
    done

    log "--- VM $vmid ($vm_name): ${#remote_paths[@]} files ---"

    # Build a shell script that cats each file with delimiters
    local read_script='
for f in '"$(printf "'%s' " "${remote_paths[@]}")"'; do
    printf "===FILE:%s===\n" "$f"
    if [ -f "$f" ]; then
        cat "$f" 2>/dev/null
        printf "\n===OK===\n"
    else
        printf "===MISSING===\n"
    fi
done
printf "===END===\n"
'

    local raw_json
    raw_json=$(ssh $SSH_OPTS "$PROXMOX_HOST" \
        "qm guest exec $vmid -- bash -c '$(echo "$read_script" | sed "s/'/'\\\\''/g")'" 2>/dev/null) || {
        warn "Failed to connect to VM $vmid ($vm_name)"
        return 0
    }

    # Parse the JSON output and split by delimiters
    local all_output
    all_output=$(echo "$raw_json" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if d.get('exitcode', 1) != 0 and not d.get('out-data', ''):
        sys.exit(1)
    sys.stdout.write(d.get('out-data', ''))
except Exception:
    sys.exit(1)
") || {
        warn "Failed to parse output from VM $vmid ($vm_name)"
        return 0
    }

    # Split the output by file delimiters and write each file
    local current_file="" current_content="" in_file=0
    local i=0

    while IFS= read -r line; do
        if [[ "$line" =~ ^===FILE:(.+)===$  ]]; then
            current_file="${BASH_REMATCH[1]}"
            current_content=""
            in_file=1
        elif [[ "$line" == "===OK===" ]]; then
            # Find the matching local path
            for j in "${!remote_paths[@]}"; do
                if [[ "${remote_paths[$j]}" == "$current_file" ]]; then
                    local dest="$LOCAL_ROOT/${local_paths[$j]}"
                    mkdir -p "$(dirname "$dest")"
                    # Remove trailing newline we added as delimiter
                    if [[ -n "$current_content" ]]; then
                        printf '%s' "${current_content%$'\n'}" > "$dest"
                    else
                        touch "$dest"
                    fi
                    chmod 600 "$dest"
                    log "  OK: ${local_paths[$j]}"
                    break
                fi
            done
            in_file=0
        elif [[ "$line" == "===MISSING===" ]]; then
            for j in "${!remote_paths[@]}"; do
                if [[ "${remote_paths[$j]}" == "$current_file" ]]; then
                    warn "  SKIP: $current_file (not found or unreadable)"
                    break
                fi
            done
            in_file=0
        elif [[ "$line" == "===END===" ]]; then
            break
        elif [[ $in_file -eq 1 ]]; then
            if [[ -n "$current_content" ]]; then
                current_content+=$'\n'"$line"
            else
                current_content="$line"
            fi
        fi
    done <<< "$all_output"
}

# ── VM definitions ───────────────────────────────────────────────────
# Each VM runs in the background for maximum parallelism.
# VMs 120 (main + openbao) run sequentially within their group since
# qm guest exec serializes on the QGA socket per VM.

recover_vm_120() {
    recover_from_vm_batch 120 docker-runtime-lv3 \
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

    # OpenBao on the same VM — runs sequentially (same QGA socket)
    recover_from_vm_batch 120 docker-runtime-lv3-openbao \
        /etc/lv3/openbao/init.json                        openbao/init.json
}

recover_vm_150() {
    recover_from_vm_batch 150 postgres-lv3 \
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
}

recover_vm_140() {
    recover_from_vm_batch 140 monitoring-lv3 \
        /etc/lv3/monitoring/netdata-stream-api-key         monitoring/netdata-stream-api-key.txt
}

recover_vm_110() {
    recover_from_vm_batch 110 nginx-lv3 \
        /etc/lv3/ntfy/alertmanager-password               ntfy/alertmanager-password.txt \
        /etc/lv3/headscale/api-key                        headscale/api-key.txt
}

recover_vm_160() {
    recover_from_vm_batch 160 backup-lv3 \
        /etc/lv3/proxmox-backup/backup-lv3-token.json     proxmox-backup/backup-lv3-token.json
}

# ── Run all VMs in parallel ──────────────────────────────────────────
log "Starting parallel recovery from all VMs..."
start_time=$(date +%s)

recover_vm_120 &
recover_vm_150 &
recover_vm_140 &
recover_vm_110 &
recover_vm_160 &

wait

end_time=$(date +%s)
elapsed=$((end_time - start_time))

log ""
log "Recovery complete in ${elapsed}s. Review .local/ contents and test SSH access."
log "Recovered files:"
find "$LOCAL_ROOT" -type f | wc -l | xargs echo "  Total files:"
