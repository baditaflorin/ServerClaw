# Service Redundancy Tier Matrix

## Purpose

`config/service-redundancy-catalog.json` is the machine-readable declaration for ADR 0179.

It answers, for every managed service:

- which redundancy tier is currently claimed
- the service-level RTO and RPO target
- which backup sources support recovery
- where the cold or warm standby lives, if one exists
- what should trigger failover
- how failback is expected to happen

## Update Rules

Update the redundancy catalog when:

1. a service is added, removed, or materially replatformed
2. a service moves between `R0`, `R1`, `R2`, or `R3`
3. backup sources change
4. standby or replica placement changes
5. failover or failback procedure changes
6. the platform gains another failure domain and the supported maximum tier changes

Keep the declarations honest:

- `R0` means no cold or warm standby exists
- `R1` means recovery depends on cold restore or rebuild
- `R2` means a warm standby exists and is expected to participate in recovery
- `R3` must not be treated as implemented on the current single-host platform

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
- exact service-id coverage against `config/service-capability-catalog.json`
- valid tier-to-standby mapping (`R0` -> `none`, `R1` -> `cold`, `R2` -> `warm`, `R3` -> `active`)
- known standby locations for non-empty standby modes
- current platform tier ceiling versus declared failure-domain count
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

This prints the tier, RTO/RPO target, backup sources, standby location, failover trigger, and failback method for the selected service.
