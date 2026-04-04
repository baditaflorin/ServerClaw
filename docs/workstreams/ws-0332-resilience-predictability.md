# Workstream ws-0332-resilience-predictability: Compose Dependency Health Gates

- ADR: [ADR 0346](../adr/0346-compose-dependency-health-gates-as-a-repo-enforced-resilience-baseline.md)
- Title: enforce health-gated compose dependencies for more predictable service recovery
- Status: ready
- Included In Repo Version: not yet
- Implemented On: 2026-04-04
- Live Applied On: not yet
- Live Applied In Platform Version: not yet
- Branch: `codex/ws-0332-resilience-predictability`
- Worktree: `.worktrees/ws-0332-resilience-predictability`
- Owner: codex
- Depends On: `ADR 0064`, `ADR 0107`, `ADR 0204`, `ADR 0246`, `ADR 0319`
- Conflicts With: none

## Scope

- turn compose dependency health gates into an explicit repository contract instead of an ad hoc role-by-role convention
- extend service completeness so compose services with local dependencies must either declare a health-gated startup path or carry a time-bounded suppression
- fix the safe runtime templates that still used blind dependency startup ordering
- document the remaining bounded exception where the upstream image does not yet expose a safe in-container health probe path

## Planned Outcome

- `scripts/service_completeness.py` will fail compose services that use `depends_on` without a matching `condition: service_healthy` gate unless the gap is explicitly time-boxed in `config/service-completeness.json`.
- `dozzle`, `minio`, and `searxng` will converge with health-gated local dependencies in their compose templates.
- `platform_context_api` will carry an explicit short-lived suppression until the Qdrant image path is given a safe governed health probe contract.
- `docs/runbooks/compose-runtime-resilience.md` will explain how to verify, fix, or time-box dependency gating gaps so future outages do not reintroduce the same startup races silently.

## Outcome

- `scripts/service_completeness.py` now enforces `Dependency health gate` for compose services that declare `depends_on`, which makes blind startup ordering a repository-visible contract violation.
- `dozzle`, `minio`, and `searxng` now ship health-gated dependency startup in their compose templates.
- `platform_context_api` is explicitly time-boxed through `2026-05-15` while the current Qdrant image path still lacks a safe governed in-container health probe contract.
- `docs/runbooks/compose-runtime-resilience.md` captures the operator path for validating, fixing, or time-boxing future dependency-gating gaps.

## Verification

- `python3 scripts/validate_service_completeness.py --validate`
- `python3 scripts/validate_service_completeness.py --service dozzle --service minio --service platform_context_api --service searxng`
- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_validate_service_completeness.py tests/test_dozzle_runtime_role.py tests/test_minio_runtime_role.py tests/test_searxng_runtime_role.py`
- `python3 scripts/workstream_registry.py --check`
- `uv run --with pyyaml python3 scripts/workstream_surface_ownership.py --validate-registry`
- `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models`
