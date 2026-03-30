# Workstream ws-0278-live-apply: ADR 0278 Live Apply From Latest `origin/main`

- ADR: [ADR 0278](../adr/0278-gotenberg-as-the-document-to-pdf-rendering-service.md)
- Title: private Gotenberg document-to-PDF rendering service live apply
- Status: live_applied
- Implemented In Repo Version: 0.177.92
- Live Applied In Platform Version: 0.130.61
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0278-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0278-live-apply`
- Owner: codex
- Depends On: `adr-0092-unified-platform-api-gateway`, `adr-0151-n8n-as-the-external-app-connector-fabric`, `adr-0199-outline-living-knowledge-wiki`, `adr-0254-serverclaw-as-a-distinct-self-hosted-agent-product-on-lv3`, `adr-0274-minio-as-the-s3-compatible-object-storage-layer`, `adr-0275-apache-tika-server-for-document-text-extraction-in-the-rag-pipeline`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0278-live-apply.md`, `docs/adr/0278-gotenberg-as-the-document-to-pdf-rendering-service.md`, `docs/runbooks/configure-gotenberg.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `Makefile`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/image-catalog.json`, `config/service-completeness.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/command-catalog.json`, `config/workflow-catalog.json`, `config/grafana/dashboards/gotenberg.json`, `config/alertmanager/rules/gotenberg.yml`, `playbooks/gotenberg.yml`, `playbooks/services/gotenberg.yml`, `collections/ansible_collections/lv3/platform/roles/gotenberg_runtime/`, `tests/test_gotenberg_runtime_role.py`, `receipts/image-scans/`, `receipts/live-applies/`, `docs/adr/.index.yaml`

## Scope

- add the repo-managed private Gotenberg runtime, firewall exposure, health probes, dashboard, alerting, SLO, and data-catalog surfaces
- refresh the shared API gateway so authenticated callers can use `/v1/gotenberg` without publishing a dedicated public hostname
- live-apply the service from an isolated latest-main worktree, verify Chromium and LibreOffice render paths end to end, and leave merge-safe receipts plus ADR metadata behind

## Verification

- `uv run --with pytest --with pyyaml pytest tests/test_gotenberg_runtime_role.py -q` returned `11 passed in 0.41s`
- `make syntax-check-gotenberg` passed
- `uvx --from pyyaml python scripts/ansible_scope_runner.py validate` passed
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate` passed
- `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --service gotenberg` and `--check-live-apply --service gotenberg` both passed
- `uv run --with pyyaml python scripts/standby_capacity.py --service gotenberg` approved the cold-standby declaration
- `uv run --with pyyaml --with jsonschema python scripts/service_completeness.py --service gotenberg` passed
- `uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:gotenberg` passed
- `./scripts/validate_repo.sh agent-standards` passed
- `./scripts/validate_repo.sh generated-docs` currently fails exactly because canonical truth is stale for protected mainline surfaces `changelog.md` and `versions/stack.yaml`, which must wait for the exact-main integration step

## Live Apply Outcome

- `make converge-gotenberg` completed successfully from source commit `8613ecf8fa4b5f43124bcc404acb1d7fd1213b36` with recap `docker-runtime-lv3 : ok=256 changed=113 unreachable=0 failed=0 skipped=28 rescued=1 ignored=0`
- the branch-local replay exposed and fixed four real defects before the successful run:
  missing `playbooks/gotenberg.yml` scope registration, wrong service-topology lookup scope inside the role defaults, Docker bridge-network creation failing on the guest because `DOCKER-FORWARD` was absent, and Chromium HTML uploads requiring `filename=index.html`
- the private runtime now answers `http://127.0.0.1:3007/health` on `docker-runtime-lv3` and both local conversion paths return PDFs
- the authenticated gateway route `https://api.lv3.org/v1/gotenberg` now proxies both the health endpoint and a Chromium conversion request with a real bearer token from the controller-local platform-context path

## Live Evidence

- receipt: `receipts/live-applies/2026-03-30-adr-0278-gotenberg-live-apply.json`
- successful branch-local converge log: `receipts/live-applies/evidence/2026-03-30-ws-0278-converge-gotenberg-r5.txt`
- intermediate failure logs retained for auditability: `receipts/live-applies/evidence/2026-03-30-ws-0278-converge-gotenberg.txt`, `receipts/live-applies/evidence/2026-03-30-ws-0278-converge-gotenberg-r2.txt`, `receipts/live-applies/evidence/2026-03-30-ws-0278-converge-gotenberg-r3.txt`, and `receipts/live-applies/evidence/2026-03-30-ws-0278-converge-gotenberg-r4.txt`
- private-service verification evidence:
  `receipts/live-applies/evidence/2026-03-30-ws-0278-local-health.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0278-local-chromium.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0278-local-libreoffice.txt`
- gateway verification evidence:
  `receipts/live-applies/evidence/2026-03-30-ws-0278-gateway-health.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0278-gateway-chromium.txt`

## Mainline Integration Resolution

- exact-main integration completed from repo version `0.177.92`, and the canonical platform version now advances to `0.130.61`
- the first merged-main replay from commit `8704a9798` failed because the Docker runtime role reloaded the full nftables ruleset, flushed Docker-managed tables, and left the `DOCKER` nat chain unavailable during Gotenberg startup
- commit `e1b0ceb64` fixed the Docker runtime replay path by applying the forward-compat rules live without reloading the full nftables ruleset, after which the authoritative merged-main replay succeeded
- the canonical mainline receipt is `receipts/live-applies/2026-03-30-adr-0278-gotenberg-mainline-live-apply.json`, and the merged-main verification evidence is preserved in the `2026-03-30-ws-0278-merged-main-*` files
