# Workstream ADR 0199: Outline Living Knowledge Wiki

- ADR: [ADR 0199](../adr/0199-outline-living-knowledge-wiki.md)
- Title: deploy Outline and wire living knowledge sync automation
- Status: implemented
- Branch: `codex/ws-0199-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0199-live-apply`
- Owner: codex
- Depends On: `adr-0043-openbao`, `adr-0056-keycloak`, `adr-0077-compose-runtime-secrets-injection`, `adr-0107-platform-extension-model`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox_florin.yml`, `config/{service-capability-catalog,subdomain-catalog,health-probe-catalog,image-catalog,secret-catalog,controller-local-secrets,api-gateway-catalog,dependency-graph,slo-catalog,data-catalog,service-completeness,service-redundancy-catalog}.json`, `collections/ansible_collections/lv3/platform/roles/{outline_runtime,outline_postgres,keycloak_runtime}`, `playbooks/outline.yml`, `playbooks/services/outline.yml`, `scripts/sync_docs_to_outline.py`, `scripts/release_manager.py`, `docs/runbooks/configure-outline.md`

## Scope

- deploy Outline on `docker-runtime-lv3` with Postgres, Redis, MinIO, and Keycloak OIDC
- publish `wiki.lv3.org` through the shared NGINX edge
- create a repo-managed Outline API token and seed the living knowledge collections
- wire release-time synchronization for Outline landing and index documents

## Verification

- `python3 scripts/validate_service_completeness.py --service outline`
- `uv run --with pytest python -m pytest tests/test_outline_runtime_role.py tests/test_outline_playbook.py tests/test_outline_sync.py tests/test_keycloak_runtime_role.py tests/test_release_manager.py tests/test_generate_platform_vars.py`
- `./scripts/validate_repo.sh agent-standards`
- `./scripts/validate_repo.sh generated-portals`
- `uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:outline`
- `uv run --with pyyaml python scripts/standby_capacity.py --service outline`
- `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service outline`
- `curl -fsS https://wiki.lv3.org/_health`
- `python3 scripts/sync_docs_to_outline.py verify --base-url https://wiki.lv3.org`
- `HETZNER_DNS_API_TOKEN=... ANSIBLE_HOST_KEY_CHECKING=False ANSIBLE_LOCAL_TEMP=/tmp/proxmox_florin_server-ansible-local ANSIBLE_REMOTE_TEMP=/tmp ./scripts/run_with_namespace.sh uvx --from pyyaml python ./scripts/ansible_scope_runner.py run --inventory ./inventory/hosts.yml --playbook ./playbooks/services/outline.yml --env production -- --private-key ./.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`

## Outcome

- live apply completed and verified on `2026-03-27`
- `wiki.lv3.org` is healthy, published through the shared edge, and the managed Outline surface now contains exactly the five governed top-level collections with one landing page each
- the bootstrap path now uses the durable `outline.automation` Keycloak identity, removes the default `Welcome` collection, and deduplicates managed landing docs during sync
- merge-to-main still must update the integrated top-level `README.md` summary, bump `VERSION`, update `changelog.md`, and update `versions/stack.yaml` only when the final mainline integration and mainline live apply happen
