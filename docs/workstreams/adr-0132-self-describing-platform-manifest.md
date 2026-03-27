# Workstream ADR 0132: Self-Describing Platform Manifest

- ADR: [ADR 0132](../adr/0132-self-describing-platform-manifest.md)
- Title: Repo-generated platform manifest with schema validation, CLI access, and committed artifact output
- Status: merged
- Implemented In Repo Version: 0.140.0
- Implemented On: 2026-03-25
- Branch: `codex/adr-0132-platform-manifest-v2`
- Worktree: `.worktrees/adr-0132-v2`
- Owner: codex
- Depends On: `adr-0037-schema-validated-repository-data-models`, `adr-0087-repository-validation-gate`, `adr-0090-unified-platform-cli`, `adr-0110-platform-versioning-and-upgrade-path`, `adr-0113-world-state-materializer`
- Conflicts With: none
- Shared Surfaces: `scripts/platform_manifest.py`, `docs/schema/platform-manifest.schema.json`, `config/manifest-static.yaml`, `build/platform-manifest.json`, `scripts/lv3_cli.py`, `Makefile`

## Scope

- implement the self-describing platform manifest generator in `scripts/platform_manifest.py`
- define the committed static inputs in `config/manifest-static.yaml`
- define and enforce the manifest schema in `docs/schema/platform-manifest.schema.json`
- publish the committed artifact at `build/platform-manifest.json`
- expose manifest inspection and refresh through `lv3 manifest`
- wire manifest verification into the generated-doc and schema validation paths
- document operator usage in `docs/runbooks/platform-manifest.md`
- record the workstream in `workstreams.yaml` and update ADR 0132 implementation metadata

## Non-Goals

- implementing the live `/v1/manifest` API gateway endpoint
- writing the manifest into Postgres `manifest.current`
- introducing a live health-composite backend beyond the current repo-evidence and optional Prometheus-backed generator inputs

## Expected Repo Surfaces

- `scripts/platform_manifest.py`
- `config/manifest-static.yaml`
- `docs/schema/platform-manifest.schema.json`
- `build/platform-manifest.json`
- `scripts/lv3_cli.py`
- `Makefile`
- `scripts/validate_repo.sh`
- `config/check-runner-manifest.json`
- `config/validation-gate.json`
- `docs/runbooks/platform-manifest.md`
- `docs/workstreams/adr-0132-self-describing-platform-manifest.md`

## Expected Live Surfaces

- none; this change is repository-side only and does not bump `platform_version`

## Verification

- Run `uv run --with pytest --with pyyaml --with jsonschema pytest -q tests/test_platform_manifest.py tests/test_lv3_cli.py`
- Run `uv run --with pyyaml --with jsonschema python scripts/platform_manifest.py --check`
- Run `python3 -m py_compile scripts/platform_manifest.py scripts/lv3_cli.py tests/test_platform_manifest.py`

## Merge Criteria

- the committed manifest artifact is reproducible from repo state and validates against its schema
- `lv3 manifest show` and `lv3 manifest refresh` work without hidden context
- generated-doc and schema validation gates fail when the committed manifest drifts from source inputs
- ADR 0132 and the workstream record both show repository implementation truth

## Delivered

- added a repo-generated platform manifest pipeline with committed static inputs and a dedicated JSON schema
- published the canonical artifact at `build/platform-manifest.json`
- added CLI inspection and refresh commands under `lv3 manifest`
- wired manifest drift checks into the validation gate and documented the operator workflow
