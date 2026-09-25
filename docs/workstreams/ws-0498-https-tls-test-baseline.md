# WS-0498: HTTPS/TLS and generated-validation baselines

## Purpose

Keep the internal Proxmox HTTPS/TLS target test aligned with the hostname emitted
by the canonical certificate catalog and ensure fresh worktrees do not compare
deployment-derived platform facts when their ignored inputs are unavailable.

## Scope

- `tests/test_https_tls_assurance_targets.py`
- Fresh-worktree platform-vars and cross-cutting derived-output equivalence
  validation, with focused tests for unavailable and malformed/drifted inputs.
- Validation-gate process-group cleanup and bounded budgets for the complete
  CPU-bound schema (20 minutes) and portal (15 minutes) validation commands,
  without weakening either command.
- The schema-validation-specific policy ceiling and the deterministic tracked
  platform manifest timestamp refresh required by its authoritative checker.
- Deterministic public architecture-diagram reconciliation required by the
  generated-documentation checks.
- Workstream ownership metadata only.

## Validation

- `uv run --with pytest --with pyyaml python -m pytest tests/test_https_tls_assurance_targets.py -q`
- `make validate-generated-https-tls-assurance`
- Focused platform-vars generator and data-model tests.

## Deployment

None. This is a test-baseline repair; it changes neither production
configuration nor ignored/private generated inputs. The tracked platform
manifest is refreshed only through its repository-authoritative generator.
