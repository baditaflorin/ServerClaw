# Replaceability Scorecards

This runbook defines how ADR 0212 is kept honest in the repository.

## Scope

The governed critical product ADR set lives in `config/replaceability-review-catalog.json`.

Every ADR listed there must include both of these sections:

- `## Replaceability Scorecard`
- `## Vendor Exit Plan`

The sections use labeled bullet fields so the repo fitness function can validate them automatically.

## Required Scorecard Fields

- `Capability Definition`
- `Contract Fit`
- `Data Export / Import`
- `Migration Complexity`
- `Proprietary Surface Area`
- `Approved Exceptions`
- `Fallback / Downgrade`
- `Observability / Audit Continuity`

## Required Exit-Plan Fields

- `Reevaluation Triggers`
- `Portable Artifacts`
- `Migration Path`
- `Alternative Product`
- `Owner`
- `Review Cadence`

## Validation

Run the focused check:

```bash
python3 scripts/replaceability_scorecards.py --validate
```

Render the current governed summary:

```bash
python3 scripts/replaceability_scorecards.py --report
```

The broader repo gate now includes the same contract through:

```bash
make validate-architecture-fitness
make validate
```

## Authoring Notes

- Reference the current best capability definition the repo already has. That can be a capability ADR, a related platform ADR, a runbook, or a machine-readable catalog while ADR 0205 backfills continue.
- Keep portable artifacts concrete. Prefer exact exports, config files, API routes, and audit streams over general statements like “the data is portable”.
- If a proprietary feature is intentionally accepted, name the exception, bound it in time or scope, and record the smallest workable migration path away from it.
