# Workstream ADR 0134: Changelog Portal Content Redaction

- ADR: [ADR 0134](../adr/0134-changelog-portal-content-redaction.md)
- Title: Config-backed read-path redaction for deployment history and changelog portal content
- Status: live_applied
- Implemented In Repo Version: 0.133.0
- Implemented In Platform Version: 0.130.20
- Implemented On: 2026-03-25
- Branch: `codex/adr-0134-changelog-redaction`
- Worktree: `.worktrees/adr-0134`
- Owner: codex
- Depends On: `adr-0081-changelog-portal`, `adr-0115-mutation-ledger`
- Conflicts With: none
- Shared Surfaces: `scripts/deployment_history.py`, `scripts/generate_changelog_portal.py`, `scripts/changelog_redaction.py`, `config/changelog-redaction.yaml`, `tests/test_changelog_redaction.py`, `docs/runbooks/deployment-history-portal.md`

## Scope

- add `config/changelog-redaction.yaml` as the repository-managed redaction contract
- implement `scripts/changelog_redaction.py` for field-aware masking, stripping, and summarisation
- apply the redacted view to deployment history generation and `get-deployment-history`
- preserve mutation-audit `params`, `env_vars`, and error detail in metadata so the redactor can summarise or strip them
- validate the redaction contract in the repository data-model gate
- add focused tests that prove secret and PII filtering in both query output and rendered portal HTML

## Non-Goals

- implementing a role-gated raw portal view
- mutating historical receipt files already committed in the repository
- changing public/private hostname publication

## Verification

- `python3 -m py_compile scripts/changelog_redaction.py scripts/deployment_history.py scripts/generate_changelog_portal.py scripts/validate_repository_data_models.py`
- `uv run --with pytest --with pyyaml python -m pytest tests/test_changelog_portal.py tests/test_changelog_redaction.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`

## Delivered

- redaction is now policy-driven instead of ad hoc HTML escaping
- the deployment history query and portal render the same redacted read model
- secrets, private IPs, internal hostnames, actor emails, and raw error detail are filtered before display
- repo validation now fails if `config/changelog-redaction.yaml` is malformed or unsupported
- ADR 0134 is implemented in repository release `0.133.0`
- ADR 0134 is live on platform version `0.130.20` via the shared authenticated changelog edge
