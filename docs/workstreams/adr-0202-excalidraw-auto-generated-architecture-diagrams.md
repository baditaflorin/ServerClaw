# Workstream ADR 0202: Excalidraw Auto Generated Architecture Diagrams

- ADR: [ADR 0202](../adr/0202-excalidraw-auto-generated-architecture-diagrams.md)
- Title: Private Excalidraw publication at `draw.example.com` plus generated `.excalidraw` architecture scenes
- Status: merged
- Implemented In Repo Version: 0.177.16
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Branch: `codex/ws-0202-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/worktree-ws-0202-live-apply`
- Owner: codex
- Depends On: `adr-0038-generated-status-docs`, `adr-0075-service-capability-catalog`, `adr-0133-portal-authentication-by-default`, `adr-0136-http-security-headers`
- Conflicts With: none
- Shared Surfaces: `roles/excalidraw_runtime`, `playbooks/excalidraw.yml`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/`, `scripts/generate_diagrams.py`, `config/service-capability-catalog.json`, `inventory/host_vars/proxmox-host.yml`, `docs/runbooks/`

## Scope

- add a repo-managed `excalidraw_runtime` role and `playbooks/excalidraw.yml`
- publish `draw.example.com` through the shared authenticated NGINX edge
- generate committed `.excalidraw` architecture scenes from repo-managed platform data
- register Excalidraw in the service, subdomain, health-probe, dependency, SLO, and workflow catalogs
- document operator converge and verification steps in `docs/runbooks/configure-excalidraw.md`

## Non-Goals

- public publication of architecture diagrams
- long-term shared scene persistence beyond the committed repo artifacts
- replacing the docs portal with Excalidraw exports

## Expected Repo Surfaces

- `roles/excalidraw_runtime/`
- `playbooks/excalidraw.yml`
- `scripts/generate_diagrams.py`
- `docs/diagrams/*.excalidraw`
- `config/service-capability-catalog.json`
- `config/subdomain-catalog.json`
- `config/health-probe-catalog.json`
- `docs/runbooks/configure-excalidraw.md`
- `docs/adr/0202-excalidraw-auto-generated-architecture-diagrams.md`
- `docs/workstreams/adr-0202-excalidraw-auto-generated-architecture-diagrams.md`

## Expected Live Surfaces

- `docker-runtime` serves the Excalidraw frontend on `http://10.10.10.20:3095`
- `docker-runtime` serves the collaboration room on `http://10.10.10.20:3096`
- `draw.example.com` is published through the shared authenticated edge
- Uptime Kuma manages the `Excalidraw Public` monitor

## Verification

- Run `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_excalidraw_runtime_role.py tests/test_generate_diagrams.py tests/test_nginx_edge_publication_role.py tests/test_generate_platform_vars.py tests/test_lv3_cli.py -q`
- Run `make syntax-check-excalidraw`
- Run `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- Run `./scripts/validate_repo.sh agent-standards`
- Run `./scripts/validate_repo.sh generated-docs` and record the current workstream-branch exception if it reports the integration-only `README.md` canonical-truth rewrite
- Run the private and public curl checks from `docs/runbooks/configure-excalidraw.md`

## Merge Criteria

- Excalidraw converges repeatably from repo-managed automation
- `/socket.io/` is routed to the collaboration room through the shared authenticated edge
- the committed diagram sources are generated from repo truth, not edited by hand
- live-apply evidence is recorded without updating protected integration files on this branch

## Outcome

- merged in repo version `0.177.16`
- the repo-managed Excalidraw runtime, diagram generator, catalog wiring, and shared-edge publication are implemented and live on production
- the production rollout is recorded in `receipts/live-applies/2026-03-27-adr-0202-excalidraw-auto-generated-architecture-diagrams-live-apply.json`
- branch-local validation confirmed the new Excalidraw automation paths, and the integration step on `main` has now updated the shared release files and canonical README outputs

## Notes For The Next Assistant

- Keep the frontend collaboration-origin patch deterministic and confined to the runtime bootstrap script rather than forking the upstream image build without a stronger reason.
- `draw.example.com` depends on shared-edge path routing. Future socket-path changes belong in the generic edge template contract, not in ad hoc nginx edits.
- Treat `docs/diagrams/*.excalidraw` as generated outputs. If they drift, regenerate them from `scripts/generate_diagrams.py` and verify with `--check`.
