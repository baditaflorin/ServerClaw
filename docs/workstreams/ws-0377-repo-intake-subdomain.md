# Workstream ws-0377-repo-intake-subdomain: Repo Intake as First-Class Subdomain

- ADR: [ADR 0224](../adr/0224-self-service-repo-intake-and-agent-assisted-deployments.md)
- Title: Repo Intake first-class runtime and recovery
- Status: in progress
- Branch: `codex/repo-intake-preflight`
- Worktree: `.worktrees/codex-repo-intake-preflight`
- Owner: Codex
- Depends On: `ADR 0224`
- Conflicts With: none

## Scope

- restore the missing Repo Intake runtime behind its existing Authentik edge
- declare the NGINX-to-runtime firewall path and the derived edge upstream
- repair the governed preflight metadata referenced by `make converge-repo-intake`
- add a focused syntax check and use deployment-selected inventory for private probes
- do not expose the service's private listener or bypass the shared Authentik boundary

## Verification Plan

- `make preflight WORKFLOW=converge-repo-intake`
- `make validate`
- `make syntax-check-repo-intake`
- `uv run --with pytest pytest -q tests/test_repo_intake_workflow.py tests/test_repo_intake_runtime_role.py`
- private listener returns HTTP 200 for `/health` and `/`
- public host remains behind Authentik and reaches the healthy upstream after login

## Notes

- Live observation: the public edge reaches the Authentik boundary but the upstream is absent/refused; the runtime is not installed on the selected host.
- Current repo gate: `make preflight WORKFLOW=converge-repo-intake` reports an unknown workflow, and `make validate` fails generated platform-variable drift.
- No live deployment or edge access-policy change is performed by this workstream until the selected topology is current and repository validation passes.

## Ownership Notes

- This document was backfilled on `2026-04-11` so shared registry validation can
  resolve the active workstream entry cleanly.
- Workstream ownership was reassigned because its former branch is no longer present on origin and no pull request is open.
