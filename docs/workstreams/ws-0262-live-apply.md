# Workstream WS-0262: OpenFGA And Keycloak Delegated Authorization Live Apply

- ADR: [ADR 0262](../adr/0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization.md)
- Title: OpenFGA and Keycloak delegated authorization live apply
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0262-openfga-keycloak-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0262-openfga-keycloak-live-apply`
- Owner: codex
- Depends On: `adr-0056-keycloak-for-operator-and-agent-sso`, `adr-0043-openbao-for-secrets-transit-and-dynamic-credentials`, `adr-0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-openfga.md`, `docs/runbooks/configure-keycloak.md`, `workstreams.yaml`

## Scope

- converge the private OpenFGA runtime, PostgreSQL backend, and Proxmox-host
  Tailscale controller proxy
- extend Keycloak with the repo-managed ServerClaw operator and runtime
  confidential clients used by the delegated authorization bootstrap flow
- seed the OpenFGA store, model, tuples, and verification checks from
  repo-managed JSON contracts
- register the service in repo validation, workflow, image, dependency,
  dashboard, alerting, and controller-secret catalogs without touching the
  protected release-truth files until the exact-main integration step

## Expected Repo Surfaces

- `Makefile`
- `playbooks/openfga.yml`
- `playbooks/services/openfga.yml`
- `collections/ansible_collections/lv3/platform/roles/openfga_postgres/`
- `collections/ansible_collections/lv3/platform/roles/openfga_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/meta/argument_specs.yml`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/main.yml`
- `inventory/host_vars/proxmox_florin.yml`
- `scripts/generate_platform_vars.py`
- `config/serverclaw-authz/bootstrap.json`
- `config/serverclaw-authz/model.json`
- `scripts/serverclaw_authz.py`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/service-completeness.json`
- `config/api-gateway-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/service-redundancy-catalog.json`
- `config/image-catalog.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `config/grafana/dashboards/openfga.json`
- `config/alertmanager/rules/openfga.yml`
- `docs/runbooks/configure-openfga.md`
- `docs/runbooks/configure-keycloak.md`
- `docs/workstreams/ws-0262-live-apply.md`
- `workstreams.yaml`
- `receipts/image-scans/2026-03-29-openfga-runtime.json`
- `receipts/live-applies/`

## Expected Live Surfaces

- OpenFGA runs on `docker-runtime-lv3` and answers health and authenticated API
  requests on `http://127.0.0.1:8096`
- the Proxmox host publishes the controller-private OpenFGA URL at
  `http://100.64.0.1:8014`
- Keycloak issues a password-grant token for `serverclaw-operator-cli` and a
  client-credentials token for `serverclaw-runtime`
- the repo-managed bootstrap store, model, tuples, and check set verify cleanly
  against the live OpenFGA runtime
- the shared API gateway can expose `/v1/openfga` after its follow-up converge

## Verification Plan

- `make generate-platform-vars`
- `make syntax-check-openfga`
- `uv run --with pytest --with pyyaml python -m pytest tests/test_openfga_postgres_role.py tests/test_openfga_runtime_role.py tests/test_serverclaw_authz.py tests/test_keycloak_runtime_role.py tests/test_generate_platform_vars.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `uv run --with pyyaml python scripts/interface_contracts.py --validate`
- `uv run --with pyyaml python scripts/service_completeness.py --validate`
- `python3 scripts/container_image_policy.py --validate`
- `./scripts/validate_repo.sh agent-standards`
- `make converge-openfga env=production`
- `make converge-api-gateway env=production`
- direct health, authenticated API, token-issuance, and
  `scripts/serverclaw_authz.py verify` checks

## Mainline Integration

- protected integration files remain intentionally untouched until the final
  exact-main merge step: `VERSION`, `changelog.md`, `README.md`, and
  `versions/stack.yaml`
- once the branch is fully validated and live-applied, the merge-to-main step
  must update ADR 0262 metadata, release truth, platform truth, and the final
  live-apply receipt on the exact branch that lands on `main`
