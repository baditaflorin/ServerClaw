# ADR 0191: Immutable Guest Replacement for Stateful and Edge Services

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.13
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

In-place upgrades are easy to start and hard to roll back. That trade-off becomes worse for services that matter to availability:

- ingress edge nodes
- databases with standbys
- monitoring and control-plane VMs

The repository already has template-based provisioning and rollback-bundle thinking, but risky service evolution still tends to drift toward mutation of long-lived machines rather than replacement of them.

## Decision

For stateful and edge services at redundancy tier `R1` or higher, the default change path will be **immutable guest replacement** rather than in-place mutation.

### Replacement model

The standard sequence is:

1. build or refresh the target image or template
2. provision a new guest with the intended configuration
3. join it as standby, preview target, or inactive edge peer
4. validate health and synthetic transactions
5. cut over traffic or leadership
6. retain the previous guest for a short rollback window

### When in-place change is allowed

In-place mutation is reserved for:

- emergency security fixes where replacement would be slower than the acceptable risk window
- low-tier services explicitly classified as rebuild-only
- narrow configuration changes already proven reversible

## Implementation

### Policy catalog

The repository now records ADR 0191 policy decisions in `config/immutable-guest-replacement-catalog.json`, validated by `docs/schema/immutable-guest-replacement-catalog.schema.json`.

Each governed entry binds a service to:

- the guest that must be treated as the replacement boundary
- its redundancy and service classification
- the expected validation mode before cutover
- the rollback retention window

### Planner and live-apply guard

`scripts/immutable_guest_replacement.py` is the operator entry point for ADR 0191. It validates the catalog, prints a replacement plan for a governed service, and enforces a failed-closed preflight for the production `live-apply-service` path.

The `Makefile` now exposes:

- `make immutable-guest-replacement-plan service=<service-id>`
- an ADR 0191 preflight inside `make live-apply-service`

When a governed service is targeted for production live apply, the preflight rejects in-place mutation unless the operator explicitly supplies `ALLOW_IN_PLACE_MUTATION=true` for the documented narrow exception path.

### Repository validation and operator guidance

`scripts/validate_repository_data_models.py` now validates the immutable replacement catalog along with the rest of the repository data models.

The operational guidance lives in:

- `docs/runbooks/immutable-guest-replacement.md`
- `docs/runbooks/deploy-a-service.md`
- `docs/runbooks/service-redundancy-tier-matrix.md`
- `docs/runbooks/validate-repository-automation.md`

These updates make the repo-side contract explicit before a full guest replacement controller exists.

## Consequences

**Positive**

- Rollback becomes much faster and less ambiguous.
- Preview and standby validation naturally fit the same delivery path used for production cutover.
- Long-lived configuration drift is reduced.

**Negative / Trade-offs**

- Immutable replacement needs more temporary capacity during upgrades.
- Stateful services still need careful replication and cutover design; replacement does not remove that complexity.
- Some legacy services will need refactoring before they can follow this path cleanly.

## Boundaries

- This ADR changes the preferred delivery pattern; it does not require every guest to become cattle overnight.
- Immutable replacement does not remove the need for backups, rehearsals, or standby validation.

## Verification

- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_immutable_guest_replacement.py tests/test_service_redundancy.py tests/test_live_apply_receipts.py`
- `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --validate`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `python3 -m py_compile scripts/immutable_guest_replacement.py scripts/validate_repository_data_models.py`
- `make immutable-guest-replacement-plan service=grafana`
- `uv run --with pyyaml --with jsonschema python scripts/immutable_guest_replacement.py --check-live-apply --service grafana`
- `make live-apply-service service=grafana env=production ALLOW_IN_PLACE_MUTATION=true EXTRA_ARGS='-e bypass_promotion=true'`
- `curl -Ik --resolve grafana.example.com:443:203.0.113.1 https://grafana.example.com/d/lv3-platform-overview/lv3-platform-overview`

The guard now fails closed for governed services. On 2026-03-27 the explicit preflight check for `grafana` returned exit code `2` and instructed the operator to use the replacement planner or acknowledge the narrow in-place exception with `ALLOW_IN_PLACE_MUTATION=true`.

The bounded production replay with the documented exception completed successfully on `monitoring` with `ok=176 changed=0 unreachable=0 failed=0 skipped=34`. The public Grafana route still returned `HTTP/2 302` to `/login`, and the local health endpoints for Grafana, Prometheus, Alertmanager, Blackbox Exporter, and Tempo all remained healthy after the replay.

The repository integration for this ADR landed on `main` in repo version `0.177.13` on 2026-03-28. `versions/stack.yaml` keeps platform version `0.130.31` because the live verification happened from the ADR workstream branch rather than from a fresh post-merge `main` replay.

## Related ADRs

- ADR 0084: Packer template pipeline
- ADR 0085: OpenTofu VM lifecycle
- ADR 0179: Service redundancy tier matrix
- ADR 0182: Live apply merge train and rollback bundle
- ADR 0188: Failover rehearsal gate for redundancy tiers
