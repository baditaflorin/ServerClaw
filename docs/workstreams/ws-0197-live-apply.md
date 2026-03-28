# Workstream WS-0197: Dify Live Apply

- ADR: [ADR 0197](../adr/0197-dify-visual-llm-workflow-canvas.md)
- Title: Live apply and end-to-end verification for the Dify visual workflow canvas
- Status: merged
- Implemented In Repo Version: 0.177.48
- Live Applied In Platform Version: 0.130.42
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0197-main-finish`
- Worktree: `.worktrees/ws-0197-main-finish`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0146-langfuse`
- Conflicts With: `adr-0198-qdrant-vector-search-semantic-rag`
- Shared Surfaces: `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/subdomain-catalog.json`, `config/subdomain-exposure-registry.json`, `config/workflow-catalog.json`, `config/controller-local-secrets.json`, `config/secret-catalog.json`, `config/image-catalog.json`, `inventory/host_vars/proxmox_florin.yml`, `scripts/api_gateway/main.py`, `config/agent-tool-registry.json`, `platform/dify-workflows/`, `docs/runbooks/configure-dify.md`, `receipts/live-applies/`

## Scope

- replay ADR 0197 from the latest `origin/main` in an isolated worktree and branch suitable for concurrent agent work
- deploy Dify on `docker-runtime-lv3` behind `agents.lv3.org` using repo-managed Ansible playbooks and pinned container images
- expose governed LV3 tools to Dify through the platform API gateway with a dedicated Dify API key flow
- verify Dify setup, tool sync, workflow import/export, and Langfuse trace configuration end to end
- record branch-local evidence, receipts, and merge guidance without touching protected integration files

## Verification

- `uv run --with pytest --with pyyaml --with requests pytest tests/test_dify_smoke.py tests/test_runbook_use_cases.py tests/test_runbook_executor.py tests/test_postgres_vm_access_policy.py -q`
- `make syntax-check-dify`
- `make syntax-check-api-gateway`
- `make validate-data-models`
- `uv run --with pyyaml python3 scripts/workstream_surface_ownership.py --validate-registry --validate-branch`
- `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`
- `make converge-dify`
- `dig +short agents.lv3.org`
- `curl -fsS -D - https://agents.lv3.org/healthz`
- `make converge-api-gateway`
- `curl -fsS -D - https://api.lv3.org/v1/health`
- `curl -sS -X POST https://api.lv3.org/v1/dify-tools/get-platform-status -H "Content-Type: application/json" -H "X-LV3-Dify-Api-Key: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/dify/tools-api-key.txt)" -d '{}'`
- `curl -fsS -D - http://127.0.0.1:18094/healthz`
- `uv run --with requests --with pyyaml python3 scripts/dify_smoke.py --base-url http://127.0.0.1:18094 --admin-email baditaflorin@gmail.com --admin-password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/dify/admin-password.txt --init-password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/dify/init-password.txt --tools-api-key-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/dify/tools-api-key.txt --export-path platform/dify-workflows/lv3-dify-smoke.yml`

## Outcome

- The rebased current-main replay completed successfully on top of release `0.177.46`, with `make converge-dify` finishing `docker-runtime-lv3 ok=111 changed=0 failed=0`, `nginx-lv3 ok=38 changed=4 failed=0`, and `postgres-lv3 ok=43 changed=4 failed=0`, followed by `make converge-api-gateway` finishing `docker-runtime-lv3 ok=234 changed=106 failed=0`.
- Public publication is now live and verified: `dig +short agents.lv3.org` returned `65.108.75.123`, `curl -fsS -D - https://agents.lv3.org/healthz` returned `HTTP/2 200`, and the Dify setup endpoint still reports `step=finished`.
- The platform API gateway replay restored packaged runbook compatibility while preserving the current ADR 0209 use-case service design, and the governed bridge now returns `HTTP/2 200` from `https://api.lv3.org/v1/dify-tools/get-platform-status` after the replay.
- The worktree-safe smoke path is now verified end to end: the linked-worktree tunnel to `127.0.0.1:18094` returned healthy JSON, `scripts/dify_smoke.py` completed with `tool_count: 11`, exported `platform/dify-workflows/lv3-dify-smoke.yml`, and reported `trace_configured: true` without a shared-repo override.
- The integrated `main` release is `0.177.48`, and receipt `2026-03-28-adr-0197-dify-mainline-live-apply` supersedes the earlier branch-local brownout receipt as the canonical merged-main evidence for ADR 0197.

## Post-Merge Follow-Up

- None. The latest-main replay, public edge publication, governed tool bridge, and linked-worktree smoke verification are now all recorded in canonical repository state.
