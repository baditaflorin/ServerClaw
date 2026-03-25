# Workstream ADR 0145: Ollama for Local LLM Inference API

- ADR: [ADR 0145](../adr/0145-ollama-for-local-llm-inference.md)
- Title: Private local LLM inference on docker-runtime-lv3, a shared platform LLM client, and bounded goal-compiler fallback routing
- Status: live_applied
- Branch: `codex/adr-0145-ollama`
- Worktree: `../proxmox_florin_server-ollama`
- Owner: codex
- Depends On: `adr-0060-open-webui-workbench`, `adr-0112-goal-compiler`, `adr-0115-mutation-ledger`
- Conflicts With: none
- Shared Surfaces: `roles/ollama_runtime`, `config/ollama-models.yaml`, `platform/llm/`, `platform/goal_compiler/compiler.py`, `inventory/host_vars/proxmox_florin.yml`, `config/workflow-catalog.json`

## Scope

- add a repo-managed `ollama_runtime` role and `playbooks/ollama.yml`
- pin the Ollama runtime image in `config/image-catalog.json`
- add the private `ollama` service to topology, health, dependency, workflow, command, and service catalogs
- add `config/ollama-models.yaml` and pull startup models during converge
- create `platform/llm/client.py` with local routing plus `llm.inference` ledger events
- integrate goal-compiler unmatched-input fallback through the shared LLM client
- wire Open WebUI to the local Ollama endpoint
- document deployment and latency verification in `docs/runbooks/configure-ollama.md`

## Non-Goals

- Publicly exposing Ollama through the nginx edge
- GPU-backed model serving or large-model scheduling
- Full Langfuse tracing from ADR 0146

## Expected Repo Surfaces

- `config/ollama-models.yaml`
- `roles/ollama_runtime/`
- `playbooks/ollama.yml`
- `platform/llm/client.py`
- `platform/goal_compiler/compiler.py`
- `scripts/ollama_probe.py`
- `docs/runbooks/configure-ollama.md`
- `docs/adr/0145-ollama-for-local-llm-inference.md`
- `docs/workstreams/adr-0145-ollama.md`

## Expected Live Surfaces

- `docker-runtime-lv3` serves `http://127.0.0.1:11434/api/version`
- `docker exec ollama ollama show llama3.2:3b` succeeds on `docker-runtime-lv3`
- Open WebUI retains successful bootstrap-admin sign-in with the local Ollama connector enabled
- a three-run probe through `scripts/ollama_probe.py` reports stable local inference latency for the startup model

## Verification

- Run `uv run --with pytest python -m pytest tests/test_ollama_runtime_role.py tests/test_platform_llm_client.py tests/unit/test_goal_compiler.py -q`
- Run `make syntax-check-ollama`
- Run `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- Run the guest-local version, model, and latency checks from `docs/runbooks/configure-ollama.md`

## Merge Criteria

- the Ollama runtime converges repeatably from the repo
- the startup model catalog is enforced during converge
- the goal compiler can use local inference without breaking deterministic rule matches
- Open WebUI remains repo-managed and private while offering the local connector

## Outcome

- `make converge-ollama` completed successfully on 2026-03-25 and pulled `llama3.2:3b`
- `make converge-open-webui` completed successfully on 2026-03-25 with the repo-managed Ollama connector enabled
- guest-local Ollama returned `{"version":"0.18.2"}` and `docker exec ollama ollama show llama3.2:3b` succeeded
- the Open WebUI container reached `http://host.docker.internal:11434/api/version`
- the three-run local generation probe measured `min=2038.3ms`, `avg=2801.9ms`, `p95=4073.5ms`, `max=4073.5ms`

## Notes For The Next Assistant

- Keep the local model boundary explicit: the Open WebUI connector is wired through `host.docker.internal`, not a shared compose network, because Ollama and Open WebUI remain separate repo-managed stacks.
- The goal-compiler fallback must stay bounded: if Ollama is unavailable, compile should degrade back to the existing parse error rather than blocking for long network timeouts.
