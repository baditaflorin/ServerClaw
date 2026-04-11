# Workstream ws-0312-main-integration

- ADR: [ADR 0312](../adr/0312-shared-notification-center-and-activity-timeline-across-human-surfaces.md)
- Title: Integrate ADR 0312 exact-main verification and validation-gate hardening onto `origin/main`
- Status: `merged`
- Included In Repo Version: 0.177.147
- Platform Version Observed During Integration: 0.130.92
- Release Date: 2026-04-02
- Branch: `codex/ws-0312-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0312-live-apply`
- Owner: codex
- Depends On: `ws-0312-live-apply`

## Purpose

Carry ADR 0312's already-verified exact-main portal rollout onto the newest
realistic `origin/main`, preserve the first implemented truth at repository
version `0.177.146` and platform version `0.130.92`, and ship the
repository-only automation hardening that the exact-main replay exposed in the
validation gate and remote execution paths.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0312-main-integration.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.147.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `scripts/validate_repo.sh`
- `scripts/gate_status.py`
- `scripts/remote_exec.sh`
- `scripts/run_gate.py`
- `scripts/run_gate_fallback.py`

## Verification

- `git fetch origin --prune` confirmed the latest realistic `origin/main`
  remained commit `d54aa2e8f2cb7ca8cbd82c9b85b4650a757ebf48`, already carrying
  ADR 0312 on repository version `0.177.146` and platform version `0.130.92`.
- Rebasing `codex/ws-0312-main-integration` onto that tip reduced the unique
  delta to four repository-automation fixes:
  atomic gate-status writes, resilient empty-JSON handling, caller-preserved
  validation-lane context, and collision-resistant remote run namespaces;
  the final merge branch also cleaned up the shared Galaxy server argument
  path in `scripts/validate_repo.sh` and removed the last Bash-4-only
  `mapfile` usage from `scripts/remote_exec.sh`.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml --with jsonschema python
  scripts/release_manager.py --bump patch ... --released-on 2026-04-02`
  prepared repository release `0.177.147` with one canonical workstream note
  and preserved platform version `0.130.92`.
- `uv run --with pytest --with fastapi --with httpx --with jinja2 --with
  itsdangerous --with python-multipart python -m pytest -q
  tests/test_interactive_ops_portal.py tests/test_ops_portal_runtime_role.py
  tests/test_ops_portal_playbook.py` returned `48 passed`.
- `uv run --with pytest python -m pytest -q tests/test_remote_exec.py
  tests/test_validation_gate.py tests/test_run_gate_fallback.py
  tests/test_validate_repo_cache.py` returned `48 passed` after the
  Bash-3-safe shell cleanups landed.
- `uv run --with pyyaml python scripts/live_apply_receipts.py --validate`
  returned `Live apply receipts OK`, `git diff --check` stayed clean, and
  `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models
  generated-docs generated-portals` completed successfully.
- `make remote-validate` passed the governed remote lane with
  `agent-standards`, `workstream-surfaces`, `ansible-syntax`,
  `schema-validation`, `policy-validation`, `iac-policy-scan`,
  `alert-rule-validation`, `type-check`, and `dependency-graph` all green.
- `make pre-push-gate` passed the final governed remote lane with
  `ansible-lint`, `yaml-lint`, `generated-docs`, `generated-portals`,
  `artifact-secret-scan`, `dependency-direction`, `security-scan`,
  `semgrep-sast`, `integration-tests`, `packer-validate`, `tofu-validate`,
  and the rest of the blocking checks green on the released tree.

## Outcome

- Release `0.177.147` carries the ADR 0312 exact-main verification follow-up
  onto `main`.
- ADR 0312 itself remains first implemented in repository version `0.177.146`
  and first verified live in platform version `0.130.92`.
- The merged mainline now hardens validation-gate automation against
  partially-written state files, removes the last Bash-4-only retention
  cleanup path from remote execution, and preserves the already-live portal
  runtime without another platform mutation.
