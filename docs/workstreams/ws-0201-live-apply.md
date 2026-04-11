# Workstream ws-0201-live-apply: ADR 0201 Live Apply From Latest `origin/main`

- ADR: [ADR 0201](../adr/0201-harbor-container-registry-with-cve-scanning.md)
- Title: Harbor runtime deployment, registry cutover, and repository automation replay from latest `origin/main`
- Status: live_applied
- Branch: `codex/ws-0201-main-final`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0201-main-merge-r2`
- Owner: codex
- Depends On: `adr-0056-keycloak`, `adr-0083-docker-check-runner`, `adr-0089-build-artifact-cache`
- Conflicts With: none
- Shared Surfaces: `inventory/host_vars/proxmox-host.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/subdomain-catalog.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/workflow-catalog.json`, `config/image-catalog.json`, `config/check-runner-manifest.json`, `config/validation-gate.json`, `config/build-server.json`, `config/windmill/scripts/check-runner-rebuild.py`, `Makefile`, `docs/runbooks/`, `receipts/live-applies/`

## Scope

- deploy Harbor on `docker-runtime` from the latest `origin/main`
- publish `registry.example.com` through the shared `nginx-edge` edge
- enable Trivy scanning, Keycloak-backed operator login, a repo-managed `check-runner` project, and a scoped Harbor robot account for check-runner publication
- migrate the current `registry.example.com/check-runner/*` images into Harbor and verify pull and push paths from `docker-build`
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
- `curl -fsS https://registry.example.com/api/v2.0/ping`
- `curl -fsS -u "admin:$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/harbor/admin-password.txt)" https://registry.example.com/api/v2.0/projects/check-runner`
- `curl -fsS -u "admin:$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/harbor/admin-password.txt)" 'https://registry.example.com/api/v2.0/projects/check-runner/repositories/python/artifacts?with_scan_overview=true&page=1&page_size=20'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' ops@10.10.10.30 'docker pull registry.example.com/check-runner/python:3.12.10 && docker images registry.example.com/check-runner/python:3.12.10 --format "{{.Repository}}:{{.Tag}} {{.ID}}"'`
- `python3 - <<'PY' ... module.main('/home/ops/builds/proxmox-host_server/.lv3-session-workspaces/ws-0201-live-apply-24eb555472/repo') ... PY` on `docker-build` returned digests for all four `check-runner/*` images after Harbor accepted push and cache uploads

## Results

- Harbor is live on `docker-runtime` and responds through `https://registry.example.com/api/v2.0/ping`.
- The shared `nginx-edge` edge now renders `registry.example.com` with `client_max_body_size 0`, `chunked_transfer_encoding on`, `proxy_request_buffering off`, and 900-second proxy timeouts for Harbor uploads.
- The `check-runner` Harbor project now reports `repo_count: 4`, all four runner repositories exist, and Harbor reports Trivy scan data on pushed artifacts.
- `docker-build` can both push and pull `registry.example.com/check-runner/*` after the split-horizon host pinning, BuildKit socket fixes, and robot-auth rebuild helper updates.
- Local repo validation is green for the touched Harbor surfaces and generated artifacts.
- On the latest replay from rebased `origin/main`, `make converge-harbor` completed with `docker-runtime : ok=126 changed=10 failed=0 skipped=20` and `nginx-edge : ok=39 changed=4 failed=0 skipped=10`.
- The latest replay re-verified `curl -fsS https://registry.example.com/api/v2.0/ping` => `Pong`, `curl -I https://registry.example.com/v2/` => `HTTP/2 401`, and `docker pull registry.example.com/check-runner/python:3.12.10` on `docker-build` => `registry.example.com/check-runner/python@sha256:9dd2ea22539ed61d0aed774d0f29d2a2de674531b80f852484849500d64169ff`.
- The Harbor replay also proved the new runtime recovery path: stale Harbor containers are now removed with a Docker daemon restart fallback, Harbor recovery now treats a missing published `8095 -> 8080` binding as unhealthy even when container health still reports `starting`, and the Harbor OIDC bootstrap now retries until Harbor finishes recovering from the compose recycle.
- The exact-main follow-up on `main` added one more Harbor readiness guard before OIDC bootstrap: if the published Harbor admin configuration API on `127.0.0.1:8095` is unreachable, the role now forces one Harbor recycle, waits for Harbor ping locally, and re-probes before continuing, which prevented the mainline replay from stalling on a stale published-port state.
- The mainline replay from commit `5c06b8ef` re-verified the public Harbor API and registry auth challenge, the runtime-local Harbor API and `/v2/` auth challenge on `docker-runtime`, and a fresh `docker pull registry.example.com/check-runner/python:3.12.10` on `docker-build` with digest `sha256:9dd2ea22539ed61d0aed774d0f29d2a2de674531b80f852484849500d64169ff`.

## Merge Follow-Through

- after `origin/main` moved forward to repo version `0.177.62` for ADR 0239, the first latest-main Harbor recheck surfaced a regression where `registry.example.com` redirected to `https://nginx.example.com/...` and `127.0.0.1:8095` on `docker-runtime` was down; replaying `make converge-harbor` from the synchronized latest-main worktree restored the Harbor runtime and shared edge publication with final recap `docker-runtime : ok=127 changed=8 failed=0 skipped=20` and `nginx-edge : ok=38 changed=3 failed=0 skipped=11`.
- the synchronized latest-main Harbor replay re-verified `curl -fsS --max-time 20 https://registry.example.com/api/v2.0/ping` => `Pong`, `curl -skI --max-time 20 https://registry.example.com/v2/` => `HTTP/2 401`, `curl -fsS --max-time 20 http://127.0.0.1:8095/api/v2.0/ping` on `docker-runtime` => `Pong`, `curl -sSI --max-time 20 http://127.0.0.1:8095/v2/` => `HTTP/1.1 401`, and `docker pull registry.example.com/check-runner/python:3.12.10` on `docker-build` => `registry.example.com/check-runner/python@sha256:9dd2ea22539ed61d0aed774d0f29d2a2de674531b80f852484849500d64169ff`.
- `main` now carries the Harbor runtime recovery hardening from commit `5c06b8ef`, Harbor is recorded on top of the synchronized latest `origin/main` baseline in repo version `0.177.63`, and the canonical exact-main receipt is `receipts/live-applies/2026-03-29-adr-0201-harbor-mainline-live-apply.json`.
- ADR 0201 first became true on platform version `0.130.43`; after ADR 0239 already advanced `main`, the Harbor merge follow-through preserves the current integrated mainline platform baseline at `0.130.45`.
