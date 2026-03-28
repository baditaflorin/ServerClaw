# Workstream ws-0201-live-apply: ADR 0201 Live Apply From Latest `origin/main`

- ADR: [ADR 0201](../adr/0201-harbor-container-registry-with-cve-scanning.md)
- Title: Harbor runtime deployment, registry cutover, and repository automation replay from latest `origin/main`
- Status: live_applied
- Branch: `codex/ws-0201-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0201-live-apply`
- Owner: codex
- Depends On: `adr-0056-keycloak`, `adr-0083-docker-check-runner`, `adr-0089-build-artifact-cache`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/subdomain-catalog.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/workflow-catalog.json`, `config/image-catalog.json`, `config/check-runner-manifest.json`, `config/validation-gate.json`, `config/build-server.json`, `config/windmill/scripts/check-runner-rebuild.py`, `Makefile`, `docs/runbooks/`, `receipts/live-applies/`

## Scope

- deploy Harbor on `docker-runtime-lv3` from the latest `origin/main`
- publish `registry.lv3.org` through the shared `nginx-lv3` edge
- enable Trivy scanning, Keycloak-backed operator login, a repo-managed `check-runner` project, and a scoped Harbor robot account for check-runner publication
- migrate the current `registry.lv3.org/check-runner/*` images into Harbor and verify pull and push paths from `docker-build-lv3`
- rerun repository automation and validation from the live platform path without touching protected integration files on this branch

## Non-Goals

- bumping `VERSION`, release sections in `changelog.md`, `versions/stack.yaml`, or the top-level integrated `README.md` on this workstream branch
- claiming final mainline release truth before merge-to-`main`

## Verification

- `uv run --with pyyaml python3 scripts/generate_adr_index.py --write`
- `python3 -m pytest -q tests/test_service_topology_filters.py`
- `make syntax-check-harbor`
- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_service_topology_filters.py tests/test_live_apply_receipts.py tests/test_remote_exec.py tests/test_validation_gate.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `python3 scripts/container_image_policy.py --validate`
- `uv run --with pyyaml python scripts/live_apply_receipts.py --validate`
- `uv run --with pyyaml python scripts/interface_contracts.py --validate`
- `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --validate`
- `make check-build-server`
- `make converge-harbor`
- `curl -fsS https://registry.lv3.org/api/v2.0/ping`
- `curl -fsS -u "admin:$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/harbor/admin-password.txt)" https://registry.lv3.org/api/v2.0/projects/check-runner`
- `curl -fsS -u "admin:$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/harbor/admin-password.txt)" 'https://registry.lv3.org/api/v2.0/projects/check-runner/repositories/python/artifacts?with_scan_overview=true&page=1&page_size=20'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' ops@10.10.10.30 'docker pull registry.lv3.org/check-runner/python:3.12.10 && docker images registry.lv3.org/check-runner/python:3.12.10 --format "{{.Repository}}:{{.Tag}} {{.ID}}"'`
- `python3 - <<'PY' ... module.main('/home/ops/builds/proxmox_florin_server/.lv3-session-workspaces/ws-0201-live-apply-24eb555472/repo') ... PY` on `docker-build-lv3` returned digests for all four `check-runner/*` images after Harbor accepted push and cache uploads

## Results

- Harbor is live on `docker-runtime-lv3` and responds through `https://registry.lv3.org/api/v2.0/ping`.
- The shared `nginx-lv3` edge now renders `registry.lv3.org` with `client_max_body_size 0`, `chunked_transfer_encoding on`, `proxy_request_buffering off`, and 900-second proxy timeouts for Harbor uploads.
- The `check-runner` Harbor project now reports `repo_count: 4`, all four runner repositories exist, and Harbor reports Trivy scan data on pushed artifacts.
- `docker-build-lv3` can both push and pull `registry.lv3.org/check-runner/*` after the split-horizon host pinning, BuildKit socket fixes, and robot-auth rebuild helper updates.
- Local repo validation is green for the touched Harbor surfaces and generated artifacts.

## Remaining For Merge To `main`

- update the protected integration files on the synchronized `main` branch: `VERSION`, release sections in `changelog.md`, canonical observed state in `versions/stack.yaml`, and the top-level `README.md` integrated status summary
- rerun `make remote-validate` from the synchronized `main` branch after canonical truth and `README.md` are updated there; on this workstream branch the remote worker reached generated-docs and then stopped on intentional branch-local canonical truth drift (`README.md`)
