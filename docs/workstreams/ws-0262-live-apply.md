# Workstream WS-0262: OpenFGA And Keycloak Delegated Authorization Live Apply

- ADR: [ADR 0262](../adr/0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization.md)
- Title: OpenFGA and Keycloak delegated authorization live apply
- Status: live_applied
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: live workstream replay pending exact-main merge
- Implemented On: 2026-03-29
- Live Applied On: 2026-03-29
- Branch: `codex/ws-0262-openfga-keycloak-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0262-openfga-keycloak-live-apply`
- Owner: codex
- Depends On: `adr-0056-keycloak-for-operator-and-agent-sso`, `adr-0043-openbao-for-secrets-transit-and-dynamic-credentials`, `adr-0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0262-openfga-and-keycloak-for-delegated-serverclaw-capability-authorization.md`, `docs/adr/.index.yaml`, `docs/runbooks/configure-openfga.md`, `docs/runbooks/configure-keycloak.md`, `workstreams.yaml`

## Scope

- converge the private OpenFGA runtime, PostgreSQL backend, and Proxmox-host
  Tailscale controller proxy
- extend Keycloak with the repo-managed ServerClaw runtime confidential client
  and stable operator identity reference used by the delegated authorization
  bootstrap flow
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
  requests on `http://127.0.0.1:8098`
- the internal OpenFGA listener must stay on `8098` because `8096` is already
  consumed by the separate `browser-runner` runtime on `docker-runtime-lv3`
- the Proxmox host publishes the controller-private OpenFGA URL at
  `http://100.64.0.1:8014`
- Keycloak issues a client-credentials token for `serverclaw-runtime` while the
  named operator remains a stable MFA-first Keycloak user reference
- the controller-side delegated-authz bootstrap uses the VM-private Keycloak
  listener at `http://10.10.10.20:8091` so live verification does not depend on
  the public `sso.lv3.org` edge route
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
- direct health, authenticated API, runtime token-issuance, and
  `scripts/serverclaw_authz.py verify` checks

## Mainline Integration

- protected integration files remain intentionally untouched until the final
  exact-main merge step: `VERSION`, `changelog.md`, `README.md`, and
  `versions/stack.yaml`
- once the branch is fully validated and live-applied, the merge-to-main step
  must update ADR 0262 metadata, release truth, platform truth, and the final
  live-apply receipt on the exact branch that lands on `main`

## Live Apply Outcome

- the workstream replay on `codex/ws-0262-openfga-keycloak-live-apply`
  finished after `make converge-openfga env=production` reconciled the
  PostgreSQL backend, the Docker runtime, the Proxmox host Tailscale proxy,
  and the delegated-authz bootstrap, with the final recap showing
  `docker-runtime-lv3 ok=236 changed=7 failed=0`,
  `localhost ok=2 changed=1 failed=0`,
  `postgres-lv3 ok=47 changed=0 failed=0`, and
  `proxmox_florin ok=38 changed=7 failed=0`
- the OpenFGA runtime now listens on `http://127.0.0.1:8098` and stays on
  `8098` by contract because the separate `browser-runner` runtime already
  occupies `8096` on `docker-runtime-lv3`
- the OpenFGA runtime role now waits for the OpenBao-rendered env contract to
  contain the expected listener addresses before the container starts, which
  prevents the stale-`8096` race that previously left the live container on the
  wrong port
- the API gateway follow-up replay now succeeds after the runtime sync stopped
  preserving controller-side archive ownership and the Keycloak verification
  token request gained the same retry pattern already used by the Keycloak
  runtime role; the final replay completed with
  `docker-runtime-lv3 ok=242 changed=113 failed=0 skipped=35`

## Live Evidence

- `curl -fsS -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openfga/preshared-key.txt)" http://100.64.0.1:8014/stores`
  returned the delegated authorization store `serverclaw-authz`
- `python3 scripts/serverclaw_authz.py verify --config config/serverclaw-authz/bootstrap.json --openfga-url http://100.64.0.1:8014 --openfga-preshared-key-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/openfga/preshared-key.txt --keycloak-url http://10.10.10.20:8091`
  returned `verification_passed: true` with the declared store, model, tuples,
  and checks all satisfied
- `curl -fsS https://api.lv3.org/healthz` now returns `{"status":"ok"}`
- the public authenticated platform catalog at
  `https://api.lv3.org/v1/platform/services` now lists the `openfga` service
  with `gateway_prefix: /v1/openfga` and the expected private internal URL
  `http://100.64.0.1:8014`
- `https://api.lv3.org/v1/openfga/healthz` now returns the canonical
  `AUTH_INSUFFICIENT_ROLE` envelope for the `lv3-agent-hub` bearer token,
  which proves the gateway route is live and protected instead of missing
- canonical branch-local live-apply receipt:
  `receipts/live-applies/2026-03-29-adr-0262-openfga-keycloak-live-apply.json`
- branch-local evidence files:
  `receipts/live-applies/evidence/2026-03-29-adr-0262-converge-openfga-live-apply.txt`
  and
  `receipts/live-applies/evidence/2026-03-29-adr-0262-converge-api-gateway-for-openfga.txt`

## Remaining For Mainline Integration

- rebase this workstream onto the latest `origin/main` tip and rerun the
  focused validation and live-apply path from that exact synchronized tree
- update the protected integration files only on the exact-main branch that
  lands on `main`: `VERSION`, `changelog.md`, `README.md`, and
  `versions/stack.yaml`
- replace the branch-local placeholder implementation metadata with the final
  merged repo version, final platform version, and canonical mainline receipt
