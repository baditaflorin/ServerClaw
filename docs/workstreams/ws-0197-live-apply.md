# Workstream WS-0197: Dify Live Apply

- ADR: [ADR 0197](../adr/0197-dify-visual-llm-workflow-canvas.md)
- Title: Live apply and end-to-end verification for the Dify visual workflow canvas
- Status: implemented
- Implemented In Repo Version: 0.177.27
- Live Applied In Platform Version: 0.130.31
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0197-main-merge`
- Worktree: `.worktrees/ws-0197-main-merge`
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

- `uv run --with pytest --with requests --with httpx --with cryptography --with fastapi pytest tests/test_api_gateway.py tests/test_api_gateway_runtime_role.py tests/test_dify_api.py tests/test_sync_tools_to_dify.py -q`
- `make syntax-check-dify`
- `make syntax-check-api-gateway`
- `make validate-data-models`
- `uv run --with pyyaml python3 scripts/workstream_surface_ownership.py --validate-registry --validate-branch`
- `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate`
- `make converge-dify EXTRA_ARGS='-e dify_skip_edge=true'`
- `uv run --with requests --with pyyaml python3 scripts/dify_smoke.py --base-url http://127.0.0.1:18094 --admin-email baditaflorin@gmail.com --admin-password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/dify/admin-password.txt --init-password-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/dify/init-password.txt --tools-api-key-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/dify/tools-api-key.txt`
- `make converge-api-gateway`
- `curl -sS -X POST https://api.lv3.org/v1/dify-tools/get-platform-status -H "Content-Type: application/json" -H "X-LV3-Dify-Api-Key: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/dify/tools-api-key.txt)" -d '{}'`
- `make validate` remains intentionally exercised but blocked on the protected branch policy that leaves the top-level README integrated status summary untouched on this workstream branch.

## Outcome

- Dify converged successfully on `docker-runtime-lv3` with the repo-managed PostgreSQL backend, runtime stack, governed tool sync scripts, and smoke workflow export path in place.
- The live runtime was verified internally through an SSH tunnel to `127.0.0.1:18094`, where `/healthz` returned healthy JSON, `/console/api/setup` reported `step=finished`, and `scripts/dify_smoke.py` completed with `tool_count: 11` and exported `platform/dify-workflows/lv3-dify-smoke.yml`.
- The platform API gateway was extended to package the workflow-contract repo surfaces needed by governed Dify tool calls, and the governed bridge now returns `HTTP/2 200` from `https://api.lv3.org/v1/dify-tools/get-platform-status` with the live Dify tools API key.
- The branch records receipt `2026-03-28-adr-0197-dify-live-apply` for the branch-local live apply, including the temporary manual OpenBao policy upsert and the `8093 -> 8094` Dify port reassignment made to avoid the pre-existing Plane proxy listener.
- The integrated `main` release is `0.177.27`, so the protected integration files are now updated and the Dify runtime, catalogs, release notes, and canonical README truth are recorded on `origin/main`.
- Public `agents.lv3.org` publication is still blocked outside the repo: `curl https://agents.lv3.org/` currently fails with `Could not resolve host: agents.lv3.org` because the Hetzner DNS write brownout prevented the edge publication step from being completed.

## Post-Merge Follow-Up

- Repo merge work is complete on `main`; the remaining task is operational, not repository integration.
- Once the Hetzner DNS write API recovers, replay the Dify edge publication from `main` without `dify_skip_edge=true`, verify DNS resolution for `agents.lv3.org`, and then record the canonical public-edge evidence on the integrated branch.
