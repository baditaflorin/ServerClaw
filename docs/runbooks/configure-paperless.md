# Configure Paperless

This runbook covers the repo-managed Paperless-ngx deployment introduced by [ADR 0285](../adr/0285-paperless-ngx-as-the-document-management-and-archive-api.md).

## Scope

The Paperless workflow converges:

- the PostgreSQL backend on `postgres-lv3`
- the Paperless runtime, Redis broker, and backup-covered state volumes on `docker-runtime-lv3`
- the public hostname `paperless.lv3.org` on the shared NGINX edge
- the dedicated Keycloak OIDC client used by the Paperless sign-in flow
- the durable Paperless API token in both controller-local secret storage and OpenBao
- the repo-managed correspondents, document types, and tags used by archive automation

docs.lv3.org remains the developer portal; Paperless intentionally publishes at `paperless.lv3.org`.

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload is already available under `.local/openbao/init.json`
- Keycloak is already deployed and healthy on `sso.lv3.org`
- Hetzner DNS API credentials are available when the edge certificate needs expansion

## Converge

On `main`, run:

```bash
HETZNER_DNS_API_TOKEN=... make live-apply-service service=paperless env=production
```

On a workstream branch where protected integration files must remain untouched, run the service playbook directly:

```bash
HETZNER_DNS_API_TOKEN=... \
ANSIBLE_HOST_KEY_CHECKING=False \
ANSIBLE_LOCAL_TEMP=/tmp/proxmox_florin_server-ansible-local \
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
curl -I https://paperless.lv3.org/
python3 scripts/paperless_sync.py verify \
  --base-url https://paperless.lv3.org \
  --api-token-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/paperless/api-token.txt \
  --desired-state-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/paperless/taxonomy.json
python3 scripts/paperless_sync.py smoke-upload \
  --base-url https://paperless.lv3.org \
  --api-token-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/paperless/api-token.txt \
  --report-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/paperless/smoke-upload-report.json
```

Guest-side verification through the Proxmox jump path:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 \
  'docker compose --file /opt/paperless/docker-compose.yml ps && curl -fsS http://127.0.0.1:8018/api/documents/?page_size=1 -H "Authorization: Token $(sudo cat /etc/lv3/paperless/api-token)"'
```

The verify command asserts that the required correspondents, document types, and tags exist. The smoke upload submits a temporary PDF through the public API, waits for ingestion, validates searchability, and then deletes the test document so the archive remains clean.
