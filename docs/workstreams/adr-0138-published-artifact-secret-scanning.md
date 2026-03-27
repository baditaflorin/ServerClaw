# Workstream ADR 0138: Published Artifact Secret Scanning

- ADR: [ADR 0138](../adr/0138-published-artifact-secret-scanning.md)
- Title: Add a dedicated secret-scanning stage for published receipts, generated search documents, and deployment-history portal artifacts
- Status: merged
- Implemented In Repo Version: 0.123.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Branch: `codex/adr-0138-published-artifact-secret-scanning`
- Worktree: `.worktrees/adr-0138`
- Owner: codex
- Depends On: `adr-0081-changelog-portal`, `adr-0087-validation-gate`, `adr-0114-incident-triage`, `adr-0121-search-indexing-fabric`
- Conflicts With: none
- Shared Surfaces: `.gitleaks.toml`, `.pre-commit-config.yaml`, `config/validation-gate.json`, `scripts/published_artifact_secret_scan.py`, `docs/runbooks/validation-gate.md`

## Scope

- create `scripts/published_artifact_secret_scan.py` as the repo-managed scanner for generated JSON and HTML artifacts
- extend `.gitleaks.toml` with platform-specific detection rules and placeholder allowlists
- add a blocking `artifact-secret-scan` entry to `config/validation-gate.json`
- add a convenience `make scan-published-artifacts` target and wire the scanner into artifact-generation targets
- document the control in a dedicated runbook and the workstream record
- add automated tests that prove dummy-secret detection and allowlist behavior

## Non-Goals

- scanning binary release artifacts
- automatic secret rotation or revocation
- retroactive redaction of already-published external systems

## Expected Repo Surfaces

- `scripts/published_artifact_secret_scan.py`
- `.gitleaks.toml`
- `.pre-commit-config.yaml`
- `config/validation-gate.json`
- `Makefile`
- `docs/adr/0138-published-artifact-secret-scanning.md`
- `docs/runbooks/published-artifact-secret-scanning.md`
- `docs/runbooks/validation-gate.md`
- `docs/workstreams/adr-0138-published-artifact-secret-scanning.md`
- `tests/test_published_artifact_secret_scan.py`

## Expected Live Surfaces

- none; this is a repository and publication-gate control

## Verification

- Run `python3 -m pytest tests/test_published_artifact_secret_scan.py tests/test_validation_gate.py -q`
- Run `python3 scripts/published_artifact_secret_scan.py --repo-root /path/to/checkout`
- Run `make scan-published-artifacts`

## Merge Criteria

- the artifact scanner fails on dummy secrets in generated receipts or published artifacts
- the scanner respects repo-defined allowlisted placeholders
- the validation gate includes a blocking published-artifact scan stage
- the runbooks explain both manual use and gate enforcement
