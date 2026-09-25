# ADR 0445: Phase 1 Multi-Deployment Hardening (example.org + example.com)

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


- Status: Superseded by ADR 0488
- Implementation Status: Not started — umbrella workstream
- Date: 2026-04-28
- Concern: multi-deployment-safety, IaC-completeness, programmatic-deploy, drift, LLM-ergonomics
- Tags: multi-deployment, ci, lint, generic-by-construction, programmatic-deploy
- Implements: subset of [20-change platform-maturity review, 2026-04-28]
- Depends on:
  - ADR 0438 (Generic-by-Construction) — ws-0438 in progress
  - ADR 0439 (Multi-Deployment Repo Architecture) — ws-0439 in progress
  - ADR 0440 (Per-Deployment Identity & Artifact Isolation) — Proposed
  - ADR 0441 (Deployment-Scoped Service Subsetting) — Proposed
  - ADR 0442 (Multi-Deployment Make Interface & Worktree Binding) — Proposed
  - ADR 0443 (Continuous Topology Reconciler) — Implemented
  - ADR 0373 (Service Registry & Derived Defaults) — 59% adoption

---

## Context

The platform is mid-refactor from "single deployment with a fork variant"
to "N independent deployments from one checkout". The last 72 hours of
convergence work (releases 0.178.222 → 0.179.4) burned through eleven
distinct failure categories during the example.org bootstrap loop, all
documented in ADR 0438. Each was a regression hole the test suite did
not catch: late-bound IP resolution before overlay, `!unsafe` blocks
that bypass Jinja, cross-role ordering coupling, hairpin NAT macro
variable scoping, Nomad OIDC field-shape assumptions, etc.

The platform currently has:

- **162 roles**, 59% on the ADR 0373 service-registry pattern, 41%
  with independent defaults.
- **190+ literal `lv3-*` / `lv3_*` identifiers** across role defaults,
  templates, and `!unsafe` blocks (ADR 0438 audit).
- **500+ pytest tests**, none of which answer "would `make converge-X
  deployment=0fork` succeed?" before merge.
- **`inventory/hosts.yml` as a hardcoded enum** of `production` /
  `staging` / `clone` — does not scale to N deployments.
- **`build/platform-manifest.json` and `build/onboarding/*` committed
  and shared** — two agents converging different deployments produce
  conflicting diffs.

A 20-change review (2026-04-28) grouped the gaps into five themes and
sequenced them into three phases. **This ADR opens Phase 1** — the
items that stop new drift, make 0fork bootstrap reproducible, and
unblock the remaining proposed multi-deployment ADRs (0440–0442).

---

## Decision

Phase 1 = six items. Items 1 and 2 are already in flight (ws-0438,
ws-0439); this ADR tracks them as cross-references and adds the four
items that have no current owner.

### Phase 1 items

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | Land ADR 0438 (generic-by-construction) — eliminate 190+ `lv3-*` literals | ws-0438 | Phases 0–3 in progress |
| 2 | Land ADR 0439/0440 — per-deployment artifact isolation | ws-0439 | In progress |
| 5 | Convert `inventory/hosts.yml` from enum to parameter | **ws-0445 (this ADR)** | New |
| 10 | Per-service convergence dry-run in pre-push gate | **ws-0445 (this ADR)** | New (subsumes ws-0438 phase 6) |
| 12 | Fork-shape fixture inventory + matrix CI | **ws-0445 (this ADR)** | New (subsumes ws-0438 phase 6) |
| 20 | Lint banning late-bound topology lookups in role defaults | **ws-0445 (this ADR)** | New (extends ADR 0443 linter) |

### Item 5 — Inventory as parameter

Replace the hardcoded `production` / `staging` / `clone` groups in
`inventory/hosts.yml` with generation from `deployment-model.yaml` keyed
on a `deployment` parameter. Make `make converge-X deployment=lv3` and
`make converge-X deployment=0fork` first-class. Coordinated with ADR
0442 (Make interface) but do not block on its full design — the
inventory generation is the load-bearing mechanism either way.

### Item 10 — Per-service convergence dry-run

Add an `ansible-playbook --check --diff` smoke run for every changed
role to the pre-push gate, executed against the fork-shape fixture
inventory (item 12). Catch the bulk of the 11 failure categories before
merge instead of during 0fork live-apply. Lifts ws-0438 phase 6
(`generic_deploy_ci`) into a first-class workstream so it is not
gated on the full 0438 sweep.

### Item 12 — Fork-shape fixture inventory + matrix CI

Two synthetic deployments under `tests/fixtures/inventories/`:

- `lv3-shape.yml` — current production identity, `lv3_*` prefix
- `0fork-shape.yml` — fork identity, `0fork_*` / `fork_*` prefix
- `synthetic-shape.yml` — third unrelated identity (`testfork.invalid`)
  to catch lv3/0fork coincidences that look generic but are not

Item 10's check runs against all three. A role passes only when all
three render successfully.

### Item 20 — Late-bound topology lookup lint

Extend `scripts/validate_no_hardcoded_topology.py` with a rule banning
`default(<production-ip-or-domain>)` patterns in role defaults
(`roles/**/defaults/main.yml`,
`collections/ansible_collections/lv3/platform/roles/**/defaults/main.yml`).
The audit category #1 from ADR 0438 (`openbao_postgres_host`
defaulting to a production IP before overlay applied) is the canonical
case. Lint rule:

- Allow: `default(omit)`, `default(undef())`, `default(<jinja-derived
  value>)`, `default(<value-from-platform_*>)`
- Deny: `default('10.10.10.X')`, `default('example.com')`,
  `default('runtime-control')`, any literal that is a known
  `proxmox_guests` IP / a known `platform_domain`.

Run advisory in the pre-push gate for one release; promote to required.

---

## Consequences

**Positive.**
- 0fork bootstrap stops being a discovery channel for regressions —
  the test matrix catches them.
- Two deployments can converge concurrently without artifact collisions.
- ADRs 0440–0442 unblock: their preconditions land here.
- The remaining 41% of roles get a structural reason to move to
  `derive_service_defaults` (item 10's dry-run will fail otherwise).

**Negative / risks.**
- Pre-push gate runtime grows. Mitigation: run dry-runs only for
  changed roles, parallelize across the three fixtures.
- `inventory/hosts.yml` regeneration touches a generated artifact that
  many tools reference — coordinate with ADR 0440 artifact isolation
  so the regeneration does not race with concurrent worktrees.
- Item 20's lint may have false positives on legitimate fallback
  patterns (e.g. dev-mode defaults). Allow-comment escape hatch with a
  `# late-bound-allow:<reason>` marker, audited monthly.

**Out of scope (Phase 2 / Phase 3).**
- Items 3, 4, 6, 11, 13, 14 (Phase 2 — multi-deployment as a parameter,
  Molecule, schema gating, receipt freshness).
- Items 7, 8, 9, 15, 16, 17, 18, 19 (Phase 3 — structural dedup, LLM
  ergonomics, traceability).

---

## Sequencing

| Step | Item | Target version |
|---|---|---|
| 1 | Item 12 — fixture inventories committed | 0.179.x |
| 2 | Item 10 — dry-run helper script + advisory CI | 0.179.x |
| 3 | Item 20 — late-bound lookup lint (advisory) | 0.180.x |
| 4 | Item 5 — `inventory/hosts.yml` parameterization | 0.180.x |
| 5 | Item 10 — promote dry-run to required | 0.181.x |
| 6 | Item 20 — promote lint to required | 0.181.x |

Items 1 (ws-0438) and 2 (ws-0439) ship on their own cadence; this ADR
tracks their status but does not redefine their plans.

---

## Acceptance Criteria

- `tests/fixtures/inventories/{lv3,0fork,synthetic}-shape.yml` exist,
  each renders the full `platform_service_registry` without error.
- `scripts/converge_dry_run.py` (or equivalent) executes
  `ansible-playbook --check --diff` for every changed role against the
  three fixtures, runs in the pre-push gate, and is promoted from
  advisory to required by 0.181.
- `scripts/validate_no_hardcoded_topology.py` flags
  `default('<known-prod-IP-or-domain>')` patterns in role defaults,
  passes on `main` after Phase 1 cleanup, and is promoted to required
  by 0.181.
- `make converge-X deployment=0fork` and `make converge-X
  deployment=lv3` are first-class entry points; the legacy `env=...`
  enum is deprecated with a one-release warning window.
- ADR 0438 phase 6 is retired or restructured to depend on this ADR's
  artifacts (no duplicate ownership).

---

## References

- ADR 0438 (Generic-by-Construction) — failure-category audit
- ADR 0439 (Multi-Deployment Repo Architecture)
- ADR 0440 (Per-Deployment Identity & Artifact Isolation)
- ADR 0442 (Multi-Deployment Make Interface)
- ADR 0443 (Continuous Topology Reconciler)
- ADR 0373 (Service Registry & Derived Defaults)
- 20-change platform-maturity review, 2026-04-28 (session record)
