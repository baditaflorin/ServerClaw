# Workstream WS-0211: Shared Policy Packs And Rule Registries Live Apply

- ADR: [ADR 0211](../adr/0211-shared-policy-packs-and-rule-registries.md)
- Title: Centralize repeated platform policy rules into one machine-checked registry and replay the governed automation paths from an isolated latest-main worktree
- Status: merged
- Implemented In Repo Version: 0.177.36
- Live Applied In Platform Version: 0.130.37
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0211-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0211-live-apply`
- Owner: codex
- Depends On: `adr-0179-service-redundancy-tier-matrix`, `adr-0180-standby-capacity-reservation-and-placement-rules`, `adr-0184-failure-domain-labels-and-anti-affinity-policy`, `adr-0192-separate-capacity-classes-for-standby-recovery-and-preview-workloads`
- Conflicts With: none
- Shared Surfaces: `config/shared-policy-packs.json`, `docs/schema/shared-policy-packs.schema.json`, `scripts/shared_policy_packs.py`, `scripts/service_redundancy.py`, `scripts/standby_capacity.py`, `scripts/capacity_report.py`, `scripts/failure_domain_policy.py`, `scripts/environment_topology.py`, `scripts/validate_repository_data_models.py`, `docs/runbooks/`, `docs/adr/0211-shared-policy-packs-and-rule-registries.md`, `docs/adr/.index.yaml`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- add one machine-checkable shared policy registry for redundancy tiers, capacity classes, and placement policies
- remove hand-edited duplicated rule sets from validators, schemas, and runbooks where the registry should be canonical
- replay the affected repository validation and live-apply automation paths from the isolated worktree
- record merge-safe evidence and any remaining main-only integration work explicitly

## Non-Goals

- changing the underlying redundancy, capacity, or placement decisions themselves
- rewriting unrelated release metadata on the workstream branch
- introducing a broad new policy engine beyond the currently duplicated rule surfaces

## Expected Repo Surfaces

- `config/shared-policy-packs.json`
- `docs/schema/shared-policy-packs.schema.json`
- `scripts/shared_policy_packs.py`
- `scripts/service_redundancy.py`
- `scripts/standby_capacity.py`
- `scripts/capacity_report.py`
- `scripts/failure_domain_policy.py`
- `scripts/environment_topology.py`
- `scripts/validate_repository_data_models.py`
- `docs/schema/service-redundancy-catalog.schema.json`
- `docs/schema/capacity-model.schema.json`
- `docs/schema/environment-topology.schema.json`
- `docs/runbooks/capacity-model.md`
- `docs/runbooks/capacity-classes.md`
- `docs/runbooks/service-redundancy-tier-matrix.md`
- `docs/runbooks/failure-domain-policy.md`
- `tests/test_shared_policy_packs.py`

## Expected Live Surfaces

- the governed `live-apply-service` preflight uses the shared policy registry for redundancy and standby checks
- repository data-model validation consumes the shared policy registry directly
- no hand-edited runtime policy drift remains between the affected repo validators

## Verification

- `uv run --with pytest --with jsonschema --with pyyaml pytest -q tests/test_shared_policy_packs.py tests/test_capacity_report.py tests/test_service_redundancy.py tests/test_standby_capacity.py tests/test_failure_domain_policy.py`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh data-models generated-docs generated-portals agent-standards`
- `uvx --from pyyaml python scripts/interface_contracts.py --check-live-apply service:headscale`
- `uv run --with pyyaml python scripts/standby_capacity.py --service headscale`
- `uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service headscale`
- `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service headscale`
- `python3 scripts/promotion_pipeline.py --emit-bypass-event --service headscale --actor-id "${USER:-unknown}" --correlation-id "break-glass:service:headscale:$(date -u +%Y%m%dT%H%M%SZ)"`
- `ANSIBLE_HOST_KEY_CHECKING=False ANSIBLE_LOCAL_TEMP=/tmp/proxmox_florin_server-ansible-local ANSIBLE_REMOTE_TEMP=/tmp LV3_RUN_ID=ws0211headscale2 scripts/run_with_namespace.sh uvx --from pyyaml python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --playbook playbooks/services/headscale.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e bypass_promotion=true`
- `curl -fsS -o /dev/null -w '%{http_code}\n' https://headscale.lv3.org/health`
- `curl -Ik https://headscale.lv3.org/health`

## Outcome

- The canonical policy registry now lives in `config/shared-policy-packs.json`, with `docs/schema/shared-policy-packs.schema.json` and `scripts/shared_policy_packs.py` defining the machine-checked contract consumed by the affected validators and reports.
- The duplicated redundancy, capacity-class, and placement enums were removed from the affected schemas and docs in favor of the shared registry, so `service_redundancy.py`, `standby_capacity.py`, `capacity_report.py`, `failure_domain_policy.py`, `environment_topology.py`, and `validate_repository_data_models.py` all resolve policy from the same source.
- The focused regression suite passed with `27 passed in 0.40s`, and repository data-model validation passed after the refactor.
- The initial fresh-worktree `headscale` replay exposed one real automation gap: `lv3.platform.nginx_edge_publication` expects `build/changelog-portal/` and `build/docs-portal/` to exist even in a brand-new worktree. Running `make generate-ops-portal generate-changelog-portal docs` populated those artifacts from committed automation, and the immediate replay then completed successfully with `localhost ok=16 changed=0 failed=0`, `nginx-lv3 ok=72 changed=5 failed=0`, and `proxmox_florin ok=42 changed=0 failed=0`.
- After absorbing the concurrent ADR 0210 `0.177.35` mainline integration, ADR 0211 was recut as release `0.177.36`, replayed the same governed `headscale` path from `codex/ws-0211-main-merge`, and completed successfully with `localhost ok=16 changed=0 failed=0`, `nginx-lv3 ok=71 changed=4 failed=0`, and `proxmox_florin ok=42 changed=0 failed=0`.
- The final edge verification passed with `https://headscale.lv3.org/health` returning `HTTP 200` from both the branch-local and merged-main replays, confirming the shared policy registry changes did not regress the governed live-apply path or the public edge publication for the selected safe service target.
- The final integrated validation bundle passed end to end: `./scripts/validate_repo.sh data-models generated-docs generated-portals agent-standards` and the expanded regression slice covering the shared policy registry plus dependency-graph generation contract (`33 passed` on the rebased `0.177.36` candidate).
- During that final verification, the repository automation was tightened so `scripts/generate_dependency_diagram.py` and `scripts/generate_docs_site.py` now share the same dependency-graph page format, and `docs/diagrams/agent-coordination-map.excalidraw` was refreshed to keep generated-doc validation deterministic.
- The canonical platform versions for ADR 0211 are now `0.177.36` in-repo and `0.130.37` on-platform, with the merged-main receipt `receipts/live-applies/2026-03-28-adr-0211-shared-policy-packs-and-rule-registries-mainline-live-apply.json` as the source of truth for the final integration state.

## Remaining For Merge To `main`

- None. The protected integration files were updated during the merged-main `0.177.36` release step, and the canonical live platform version remained `0.130.37` after the verified replay.
