# Service Redundancy Tier Matrix

## Purpose

`config/service-redundancy-catalog.json` is the machine-readable declaration for ADR 0179.
The canonical tier order, standby-kind mapping, rehearsal tier sequence, and live-apply modes now live in `config/shared-policy-packs.json`.

It answers, for every managed service:

- which redundancy tier is currently claimed
- which redundancy tier is currently implemented from fresh rehearsal evidence
- the service-level RTO and RPO target
- which backup sources support recovery
- where the cold or warm standby lives, if one exists
- what should trigger failover
- how failback is expected to happen
- which rehearsal evidence currently keeps the claim trustworthy

## Update Rules

Update the redundancy catalog when:

1. a service is added, removed, or materially replatformed
2. a service moves between `R0`, `R1`, `R2`, or `R3`
3. backup sources change
4. standby or replica placement changes
5. failover or failback procedure changes
6. the platform gains another failure domain and the supported maximum tier changes
7. rehearsal freshness policy changes
8. a rehearsal passes, fails, or expires and the implemented claim needs to move

Keep the declarations honest:

- `R0` means no cold or warm standby exists
- `R1` means recovery depends on cold restore or rebuild
- `R2` means a warm standby exists and is expected to participate in recovery
- `R3` must not be treated as implemented on the current single-host platform

Keep the implemented claim honest:

- `R1` requires a fresh restore-to-preview rehearsal
- `R2` requires a fresh standby switchover or promotion rehearsal
- `R3` requires a fresh cross-domain failover rehearsal
- if the latest required rehearsal is missing, stale, or failed, status reporting falls back to the highest lower tier with a fresh passing proof, or to `R0` if none exists

## Validation

Run:

```bash
uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --validate
```

Or use:

```bash
make validate
```

Validation checks:

- JSON Schema validity and required fields
- policy values resolved from `config/shared-policy-packs.json`
- exact service-id coverage against `config/service-capability-catalog.json`
- valid tier-to-standby mapping (`R0` -> `none`, `R1` -> `cold`, `R2` -> `warm`, `R3` -> `active`)
- known standby locations for non-empty standby modes
- current platform tier ceiling versus declared failure-domain count
- declared rehearsal gate defaults for `R1`, `R2`, and `R3`
- rehearsal-proof structure for trigger, target environment, duration, observed RTO, data-loss or lag note, health verification, rollback result, and evidence reference
- immutable guest replacement policies still validate for the governed production guests

## Live Apply Guard

Before `live-apply-service`, `live-apply-group`, or `live-apply-site` runs Ansible, the Make target now calls:

```bash
uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply
```

Or for one service:

```bash
uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --check-live-apply --service postgres
```

That preflight:

- validates the catalog
- resolves the deployment mode implied by each service tier
- prints the declared tier, platform-supported tier, and currently implemented tier from fresh rehearsal evidence
- rejects any service that claims a tier above what the current platform can honestly support

ADR 0191 adds a second production guard for governed guests:

```bash
uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service grafana
```

That guard layers on top of the redundancy tier matrix and blocks in-place production mutation when the service's guest is required to roll out by immutable replacement unless the operator sets the documented narrow exception path.

## Querying One Service

```bash
uv run --with pyyaml --with jsonschema python scripts/service_redundancy.py --service postgres
```

This now prints the declared tier, implemented tier, rehearsal-gate status, rehearsal requirements, recorded proofs, RTO/RPO target, backup sources, standby location, failover trigger, and failback method for the selected service.

## Recording Rehearsal Evidence

For every `R1` or higher rehearsal, record at least:

- trigger and target environment
- duration and observed RTO
- data-loss or replication-lag observation
- health verification results
- rollback or failback result
- a repo-relative evidence reference, usually a structured live-apply receipt or branch-local evidence note

When the latest proof does not pass, keep it in the catalog anyway so status reporting can downgrade the implemented claim without hiding the failed exercise.
If the redundancy tier vocabulary changes, update `config/shared-policy-packs.json` instead of editing duplicate enums in multiple schema and script files.
