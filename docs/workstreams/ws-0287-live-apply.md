# Workstream ws-0287-live-apply: ADR 0287 Live Apply From Latest `origin/main`

- ADR: [ADR 0287](../adr/0287-woodpecker-ci-as-the-api-driven-continuous-integration-server.md)
- Title: deploy Woodpecker CI as the API-driven continuous integration server
- Status: blocked
- Branch: `codex/ws-0287-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0287-live-apply`
- Owner: codex
- Depends On: `adr-0042`, `adr-0077`, `adr-0107`, `adr-0143`
- Conflicts With: none

## Scope

- add the repo-managed Woodpecker server and agent on `docker-runtime-lv3`
- provision the dedicated PostgreSQL database, Gitea OAuth bootstrap, OpenBao-backed runtime secrets, and `ci.lv3.org` edge publication
- define the repository-root `.woodpecker.yml` validation pipeline and seed the `ops/proxmox_florin_server` repository activation plus CI smoke secret through the Woodpecker API
- live-apply the change from this isolated latest-main worktree, verify the API-driven workflow end to end, and leave merge-safe receipts plus ADR metadata behind

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0287-live-apply.md`
- `docs/adr/0287-woodpecker-ci-as-the-api-driven-continuous-integration-server.md`
- `docs/runbooks/configure-woodpecker.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `playbooks/woodpecker.yml`
- `playbooks/services/woodpecker.yml`
- `collections/ansible_collections/lv3/platform/playbooks/woodpecker.yml`
- `collections/ansible_collections/lv3/platform/roles/woodpecker_postgres/`
- `collections/ansible_collections/lv3/platform/roles/woodpecker_runtime/`
- `platform/ansible/woodpecker.py`
- `scripts/woodpecker_bootstrap.py`
- `scripts/woodpecker_tool.py`
- `.woodpecker.yml`
- `config/api-gateway-catalog.json`
- `config/certificate-catalog.json`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/service-completeness.json`
- `config/subdomain-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/dependency-graph.json`
- `config/service-redundancy-catalog.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `config/correction-loops.json`
- `config/uptime-kuma/monitors.json`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/grafana/dashboards/slo-overview.json`
- `Makefile`
- `tests/test_generate_platform_vars.py`
- `tests/test_postgres_vm_access_policy.py`
- `tests/test_woodpecker_client.py`
- `tests/test_woodpecker_playbook.py`
- `tests/test_woodpecker_runtime_role.py`
- `receipts/image-scans/`
- `receipts/live-applies/`
- `docs/adr/.index.yaml`

## Verification

- `make validate-generated-vars`
- `make syntax-check-woodpecker`
- `uv tool run --from ansible-lint ansible-lint playbooks/woodpecker.yml playbooks/services/woodpecker.yml collections/ansible_collections/lv3/platform/roles/woodpecker_postgres collections/ansible_collections/lv3/platform/roles/woodpecker_runtime collections/ansible_collections/lv3/platform/playbooks/woodpecker.yml`
- `./scripts/validate_repo.sh json health-probes data-models agent-standards`
- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_generate_platform_vars.py tests/test_postgres_vm_access_policy.py tests/test_woodpecker_playbook.py tests/test_woodpecker_runtime_role.py tests/test_woodpecker_client.py tests/test_validate_service_catalog.py tests/test_validate_service_completeness.py tests/test_subdomain_catalog.py tests/test_service_redundancy.py tests/test_workstream_surface_ownership.py tests/test_ansible_execution_scopes.py tests/test_ansible_role_idempotency.py tests/test_data_catalog.py tests/test_subdomain_exposure_audit.py -q`
- `HETZNER_DNS_API_TOKEN=... make converge-woodpecker env=production` reached the live Hetzner DNS mutation step and then failed while creating the `ci.lv3.org` A record because the legacy `dns.hetzner.com` write API returned the published brownout/shutdown response.

## Blocker

- Latest realistic upstream remains `origin/main` commit `4db2d1f4dc788fa391f3cf1bf39facfcac00c218`.
- The first live replay from this worktree is recorded in `receipts/live-applies/evidence/2026-03-30-ws-0287-live-apply-r1.txt`.
- Direct provider probes reproduced the failure outside the Ansible wrapper: the legacy Hetzner DNS `POST /records` call for `ci.lv3.org -> 65.108.75.123` returned a brownout payload with provider error code `503`.
- Because `playbooks/woodpecker.yml` performs the Hetzner DNS reconcile before the PostgreSQL/runtime/bootstrap stages, the Woodpecker runtime itself is not yet live on this branch.
- Completion now requires one of:
  - a successful rerun after the provider brownout ends, while the legacy DNS token still works
  - or a Hetzner Console API token plus the broader DNS-API migration path for `lv3.org`

## Remaining For Merge-To-Main

- Do not update `VERSION`, release sections in `changelog.md`, the top-level integrated `README.md` summary, or `versions/stack.yaml` on this branch.
- The protected integration files still must wait for the final exact-main replay.
- Before merge-to-`main`, rerun `make converge-woodpecker env=production`, verify `http://100.64.0.1:8017/healthz`, `https://ci.lv3.org/healthz`, `make woodpecker-manage ACTION=whoami`, `make woodpecker-manage ACTION=list-secrets WOODPECKER_ARGS='--repo ops/proxmox_florin_server'`, and `make woodpecker-manage ACTION=trigger-pipeline WOODPECKER_ARGS='--repo ops/proxmox_florin_server --branch main --wait'`.
