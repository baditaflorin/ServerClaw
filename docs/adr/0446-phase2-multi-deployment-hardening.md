# ADR 0446: Phase 2 Multi-Deployment Hardening (receipt freshness + Molecule)

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


- Status: Superseded by ADR 0488
- Implementation Status: Not started — umbrella workstream
- Date: 2026-04-28
- Concern: drift, programmatic-deploy, multi-deployment-safety, role-coverage
- Tags: multi-deployment, receipts, molecule, programmatic-deploy
- Implements: subset of [20-change platform-maturity review, 2026-04-28]
- Depends on:
  - ADR 0445 (Phase 1 multi-deployment hardening) — shipped 0.179.6
  - ADR 0438 (Generic-by-Construction) — ws-0438 in progress
  - ADR 0439–0442 (multi-deployment substrate) — ws-0439 substrate shipped
  - ADR 0443 (Continuous Topology Reconciler) — Implemented

---

## Context

Phase 1 (ADR 0445) shipped the fork-shape fixture matrix, per-service
convergence dry-run, late-bound-default lint, and the deployment-loader
integration test. The 20-change review enumerated six Phase 2 items
(3, 4, 6, 11, 13, 14). Survey of the current codebase (2026-04-28)
shows four of those have substrate already in place:

| # | Item | Status |
|---|---|---|
| 3 | Service profiles (ADR 0441) | Substrate shipped via ws-0439 (`scripts/deployment.py::resolve_enabled_services`, `config/contracts/deployment-v1/profile.schema.json`) |
| 4 | Make interface + worktree binding (ADR 0442) | Substrate shipped via ws-0439 (`MULTI_DEPLOYMENT_ENABLED=1` flag, `DEPLOYMENT_ARG`) |
| 6 | Migrate remaining roles to `derive_service_defaults` | In flight via ws-0438 (Phase 2 sweep, 67 stragglers remaining) |
| 13 | Schema-validate generated artifacts at gate time | Substrate present (`validate_repo.sh` runs ~25 validators including `validate_repository_data_models.py` with jsonschema; `validate_service_registry.py`, `validate_service_completeness.py`) |

Two items have **no current owner** and are this ADR's scope:

- **Item 14 — Receipt freshness check.** `versions/stack.yaml` carries
  `live_apply_evidence.latest_receipts` for every service. Many entries
  are 1+ month old (`monitoring: 2026-03-28`, `nats_jetstream: 2026-03-30`).
  No automation flags a service whose code has changed but whose
  receipt has not. This is the canonical drift signal for "the service
  diverged on disk but nobody re-converged it." Currently you only
  notice when somebody hits a 502.
- **Item 11 — Molecule per-role tests.** 500+ pytest files cover
  Python helpers, scripts, validators, and integration. Zero exercise
  a single role's idempotence on a real container. The gap shows up
  every 0fork bootstrap loop: a role works in production by accident
  because state on disk papers over a missing task. ADR 0445 phase 1.2
  catches the parse-time class with `--syntax-check`; Molecule is the
  runtime equivalent.

A third deliverable falls naturally between them:

- **Bonus — `service-deployability` contract sub-test.** `validate_service_registry.py`
  already validates schema-shape. It does NOT cross-reference
  `image_catalog_key` against the actual container catalog or assert
  `host_group` exists in inventory. Items 13 and 15 from the original
  20-change review both call this out.

---

## Decision

Three deliverables, in order:

### Item 14 — `scripts/check_receipt_freshness.py`

Reads `versions/stack.yaml::live_apply_evidence.latest_receipts`, parses
the date prefix from each receipt slug (format
`YYYY-MM-DD-<slug>`), and reports the age of every receipt. Exit
codes:

- `0` — every receipt is within the freshness window
- `1` — at least one receipt exceeds the window (when invoked with `--strict`)
- `2` — invocation error (missing stack.yaml, malformed entries)

Default freshness window: 30 days. Override via
`--max-age-days <N>` or `RECEIPT_MAX_AGE_DAYS` env var. Default mode
is **advisory** — exits 0 even when stale, just prints the list — so
the gate can include it without the staleness blocking pushes during
the rollout. ADR 0446 phase 5 promotes to required.

Output is human-readable by default; `--json` returns
`{stale: [...], fresh: [...], summary: {stale: N, fresh: M, ...}}`
for downstream automation (Windmill schedule, ops_portal widget).

### Item 11 — Molecule scaffold

Create one canonical Molecule scenario for the most-changed role of the
last 30 days. Survey of recent commits points at
`mail_platform_runtime` (touched in 0.178.222–0.179.6 for fork
divergence fixes). Scaffold:

- `roles/mail_platform_runtime/molecule/default/molecule.yml` —
  scenario config (driver: docker, platform: ubuntu-22.04)
- `roles/mail_platform_runtime/molecule/default/converge.yml` —
  apply the role with the `0fork-shape.yml` fixture as `extra_vars`
- `roles/mail_platform_runtime/molecule/default/verify.yml` —
  assert role-specific invariants
- `roles/mail_platform_runtime/molecule/README.md` —
  explain the contract and how to add scenarios for other roles

This is a starter, not a full migration. ADR 0446 phase 4 expands
to the next 9 most-changed roles.

### Bonus — extend `validate_service_registry.py`

Add two cross-reference assertions:

1. Every entry's `image_catalog_key` (when service_type is
   `docker_compose`) must resolve to a real key in
   `config/image-catalog.json`.
2. Every entry's `host_group` must exist in
   `inventory/host_vars/proxmox-host.yml::proxmox_guests` (or be one
   of the inventory groups).

Today (verify): `validate_service_registry.py` line 35 references
`IMAGE_CATALOG_PATH` so #1 is partially in place. #2 may be in
`validate_topology_consistency.py` already — survey before
writing new code.

---

## Sequencing

| Step | Item | Target version |
|---|---|---|
| 1 | Item 14 — receipt freshness checker (advisory) | 0.179.x |
| 2 | Item 11 — Molecule scaffold for `mail_platform_runtime` | 0.179.x |
| 3 | Bonus — extend `validate_service_registry.py` if gaps confirmed | 0.179.x |
| 4 | Expand Molecule to next 9 most-changed roles | 0.180.x |
| 5 | Promote receipt-freshness from advisory to required | 0.181.x |

Items 3, 4, 6, 13 from the original Phase 2 list are tracked here as
done-elsewhere; this ADR does not redefine them.

---

## Acceptance Criteria

- `scripts/check_receipt_freshness.py` exists, parses
  `versions/stack.yaml`, reports per-receipt age, has `--json` and
  `--strict` modes, has unit tests for date parsing and threshold
  logic.
- One role has a working Molecule scenario that runs `make
  molecule-test svc=<role>` (or equivalent) cleanly.
- `validate_service_registry.py` either already covers
  `image_catalog_key` + `host_group` cross-refs, or is extended to.

---

## References

- ADR 0445 (Phase 1 multi-deployment hardening) — predecessor
- ADR 0443 (Continuous Topology Reconciler) — runtime drift counterpart
- ADR 0373 (Service Registry & Derived Defaults)
- 20-change platform-maturity review, 2026-04-28
