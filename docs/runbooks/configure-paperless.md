# Configure Paperless

This runbook covers the repo-managed Paperless-ngx deployment introduced by [ADR 0285](../adr/0285-paperless-ngx-as-the-document-management-and-archive-api.md).

## Scope

The Paperless workflow converges:

- the PostgreSQL backend on `postgres`
- the Paperless runtime, Redis broker, and backup-covered state volumes on `docker-runtime`
- the public hostname `paperless.example.com` on the shared NGINX edge
- the dedicated Keycloak OIDC client used by the Paperless sign-in flow
- the durable Paperless API token in both controller-local secret storage and OpenBao
- the repo-managed correspondents, document types, and tags used by archive automation

docs.example.com remains the developer portal; Paperless intentionally publishes at `paperless.example.com`.

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload is already available under `.local/openbao/init.json`
- Keycloak is already deployed and healthy on `sso.example.com`
- Hetzner DNS API credentials are available when the edge certificate needs expansion

## Converge

On `main`, run:

```bash
ALLOW_IN_PLACE_MUTATION=true \
HETZNER_DNS_API_TOKEN=... \
make live-apply-service service=paperless env=production
```

This is the required path for the authoritative platform-version bump because
`make live-apply-service` checks canonical truth before mutation and is the
exact-main replay that should settle the protected release surfaces.

`docker-runtime` is still governed by ADR 0191 immutable guest replacement,
so `ALLOW_IN_PLACE_MUTATION=true` is the documented narrow exception for this
bounded in-place Paperless replay on the shared runtime guest.

On a non-`main` workstream branch, expect that target to stop at the canonical
truth gate if protected shared integration files such as `README.md`,
`VERSION`, `changelog.md`, or `versions/stack.yaml` would need refresh. That
stop is expected branch-local behavior; use the direct scoped runner below and
record the evidence in the workstream receipt instead of editing protected
release truth on the branch.

Before replaying Paperless on the shared runtime guest, confirm no competing
automation is still mutating `docker-runtime`. A concurrent Docker restart
can terminate `paperless` and `paperless-redis` cleanly during taxonomy
verification and surface as a false `Wait for the Paperless authenticated
taxonomy endpoint` failure.

When another agent is working in parallel, take the service-scoped lock first:

```bash
make ensure-resource-lock-registry
make resource-lock-acquire \
  RESOURCE='vm:120/service:paperless' \
  HOLDER='agent:codex/ws-0285-main-integration-r2' \
  LOCK_TYPE=exclusive \
  TTL_SECONDS=3600 \
  CONTEXT_ID='ws-0285-paperless-mainline-live-apply'
```

Release it after the replay finishes:

```bash
make resource-lock-release \
  RESOURCE='vm:120/service:paperless' \
  HOLDER='agent:codex/ws-0285-main-integration-r2'
```

On a workstream branch where protected integration files must remain untouched, run the service playbook directly:

```bash
HETZNER_DNS_API_TOKEN=... \
ANSIBLE_HOST_KEY_CHECKING=False \
ANSIBLE_LOCAL_TEMP=/tmp/proxmox-host_server-ansible-local \
ANSIBLE_REMOTE_TEMP=/tmp \
./scripts/run_with_namespace.sh uvx --from pyyaml python \
  ./scripts/ansible_scope_runner.py run \
  --inventory ./inventory/hosts.yml \
  --playbook ./playbooks/services/paperless.yml \
  --env production \
  -- \
  --private-key ./.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Generated local artifacts

The workflow maintains controller-local secrets under `.local/paperless/`:

- `database-password.txt`
- `secret-key.txt`
- `redis-password.txt`
- `admin-password.txt`
- `api-token.txt`
- `taxonomy.json`
- `sync-report.json`
- `smoke-upload-report.json`

The Keycloak client secret is mirrored under `.local/keycloak/paperless-client-secret.txt`.

## Verification

Repository and syntax checks:

```bash
python3 scripts/validate_service_completeness.py --service paperless
uv run --with pytest python -m pytest \
  tests/test_paperless_runtime_role.py \
  tests/test_paperless_playbook.py \
  tests/test_paperless_metadata.py \
  tests/test_paperless_sync.py \
  tests/test_keycloak_runtime_role.py \
  tests/test_generate_platform_vars.py
./scripts/validate_repo.sh agent-standards health-probes
```

Runtime verification:

```bash
curl -I https://paperless.example.com/
python3 scripts/paperless_sync.py verify \
  --base-url https://paperless.example.com \
  --api-token-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/paperless/api-token.txt \
  --desired-state-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/paperless/taxonomy.json
python3 scripts/paperless_sync.py smoke-upload \
  --base-url https://paperless.example.com \
  --api-token-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/paperless/api-token.txt \
  --report-file /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/paperless/smoke-upload-report.json
```

Guest-side verification through the Proxmox jump path:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible \
  -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml \
  docker-runtime \
  -m shell \
  -a 'docker compose --file /opt/paperless/docker-compose.yml ps && TOKEN=$(sudo cat /etc/lv3/paperless/api-token) && curl -fsS http://127.0.0.1:8018/api/documents/?page_size=1 -H "Authorization: Token ${TOKEN}"' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

The verify command asserts that the required correspondents, document types, and tags exist. The smoke upload submits a temporary PDF through the public API, waits for ingestion, validates searchability, and then deletes the test document so the archive remains clean.

Paperless validates `Host` headers strictly. For guest-local probing, use the
loopback listener `127.0.0.1:8018` or send `Host: paperless.example.com`; direct
HTTP requests to `10.10.10.20:8018` return `400 Bad Request` by design.
