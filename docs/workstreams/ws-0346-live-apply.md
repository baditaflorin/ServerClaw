# Workstream ws-0346-live-apply: ADR 0346 Repowise Live Apply

- ADR: [ADR 0346](../adr/0346-repowise-semantic-search.md)
- Title: live apply Repowise semantic code search from the latest `origin/main`
- Status: ready
- Branch: `codex/ws-0346-live-apply`
- Worktree: `.worktrees/ws-0346-live-apply`
- Owner: codex
- Depends On: `ADR 0167`, `ADR 0198`, `ADR 0346`
- Conflicts With: none

## Scope

- replay the Repowise service from a fresh worktree based on the latest
  `origin/main`
- close the governed live-apply gap by adding the missing service wrapper and
  service-lane metadata needed for `make live-apply-service service=repowise`
- verify that worktree-based live applies load the shared `.local/identity.yml`
  overlay correctly instead of requiring a worktree-local secret copy
- capture live-apply evidence, update ADR metadata, and leave a merge-safe
  record for any exact-main integration follow-up

## Expected Repo Surfaces

- `workstreams.yaml`
- `workstreams/active/ws-0346-live-apply.yaml`
- `docs/workstreams/ws-0346-live-apply.md`
- `docs/adr/0346-repowise-semantic-search.md`
- `docs/adr/implementation-status/adr-0346.yaml`
- `docs/runbooks/configure-repowise.md`
- `config/service-capability-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `playbooks/repowise.yml`
- `playbooks/services/repowise.yml`
- `platform/ansible/execution_scopes.py`
- `tests/test_ansible_execution_scopes.py`
- `tests/test_repowise_playbook.py`
- `receipts/live-applies/2026-04-12-adr-0346-repowise-*.json`
- `receipts/live-applies/evidence/2026-04-12-ws-0346-*`

## Expected Live Surfaces

- VM `docker-runtime`
- Repowise health endpoint on `127.0.0.1:7070`
- Repowise semantic search endpoint on the same runtime
- published Repowise route through the shared edge topology

## Initial Baseline

- worktree created from `origin/main@86390fcc8a07fca2a58670f60ec4cf6b9d0278eb`
- repository version on branch start: `0.178.116`
- platform version on branch start: `0.178.77`
- archived workstream `repowise-semantic-search` already marked the feature
  `merged` but still `live_applied: false`
- the repo lacked `playbooks/services/repowise.yml`
- `config/service-capability-catalog.json` still pointed Repowise at
  `playbooks/repowise.yml` instead of the governed service wrapper
- `platform/ansible/execution_scopes.py` still resolved `.local/identity.yml`
  relative to the worktree root instead of the shared repo root

## Merge Criteria

- `make live-apply-service service=repowise env=production` runs from the fresh
  worktree without requiring a copied `.local/`
- Repowise answers locally on `docker-runtime` and returns semantic search
  results after the replay
- repository validation covers the new wrapper, scope metadata, and worktree
  identity fallback
- ADR metadata and live-apply evidence clearly record what became true live and
  which protected integration surfaces still require exact-main handling

## Progress Notes

### 2026-04-11: Worktree Baseline And Repo Gaps

- created `codex/ws-0346-live-apply` from the latest fetched `origin/main`
- confirmed the intended ADR file is `docs/adr/0346-repowise-semantic-search.md`
  even though the repo also contains older duplicate `0346` filenames for other
  historical decisions
- confirmed the prior `repowise-semantic-search` workstream already merged the
  feature code but left the live-apply state incomplete
- identified the current live-apply blockers before the first replay:
  - missing `playbooks/services/repowise.yml` wrapper for the governed service lane
  - missing `playbooks/repowise.yml` execution-scope registration
  - service catalog deployment surface still pointed at the direct playbook
  - worktree-scoped Ansible identity override still looked for
  `.worktrees/.../.local/identity.yml` instead of the shared overlay root

### 2026-04-12: Live Apply And Evidence Capture

- executed `make live-apply-service service=repowise env=production` from the
  fresh worktree after validating the governed wrapper and execution scope
- recorded live-apply evidence and receipt files for the replay, including the
  restic timeout warning captured during the governed workflow
- documented the timeout exception using `RESTIC_ALLOW_TIMEOUT=1` and added
  runbook guidance so a follow-up Restic verification can be performed once the
  repository responds again
- updated ADR 0346 metadata and implementation status to reflect the verified
  live-apply state on 2026-04-12
