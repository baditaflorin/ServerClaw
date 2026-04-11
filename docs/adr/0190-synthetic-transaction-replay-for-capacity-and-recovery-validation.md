# ADR 0190: Synthetic Transaction Replay for Capacity and Recovery Validation

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.21
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

Smoke tests answer "does it start," but they do not answer:

- how the system behaves under realistic request patterns
- whether failover materially changes user-facing latency
- whether a restored environment can keep up with representative load

The platform already has service capability catalogs, health probes, and integration tests. What it lacks is a reusable, privacy-safe workload that can be replayed against previews, restored clones, and standby targets.

## Decision

We will maintain a **synthetic transaction replay harness** for capacity, failover, and recovery validation.

### Replay sources

The replay catalog should be built from:

- synthetic user journeys created from service contracts
- sanitized recordings of common operator workflows
- representative background jobs and webhook sequences

### Validation targets

Replay runs should be supported against:

- branch preview environments
- restore rehearsal targets
- standby targets during planned switchovers

### Measured outputs

Each replay run must record:

- request success rate
- end-to-end latency distribution
- queue depth or backlog growth where relevant
- behaviour during cutover or degradation windows

## Consequences

**Positive**

- Availability changes can be judged by realistic user impact, not only process liveness.
- Restore and failover drills become much more informative.
- Capacity discussions gain a repeatable baseline for comparison.

**Negative / Trade-offs**

- Building and maintaining representative replay scenarios takes discipline.
- Synthetic transactions can still miss long-tail production behaviours.
- Replay targets need careful scoping to avoid accidental writes against shared environments.

## Boundaries

- This ADR adds workload validation; it does not replace unit, integration, or health-probe testing.
- Replays must use synthetic or sanitized inputs only.

## Related ADRs

- ADR 0096: Service uptime contracts and SLO tracking
- ADR 0111: End-to-end integration test suite
- ADR 0171: Controlled fault injection for resilience validation
- ADR 0185: Branch-scoped ephemeral preview environments
- ADR 0187: Anonymized seed data snapshots for repeatable tests

## Implementation Notes

- The repository now ships `scripts/synthetic_transaction_replay.py` plus `config/synthetic-transaction-catalog.json` as the governed replay harness for privacy-safe control-plane request sequences.
- ADR 0099 `scripts/restore_verification.py` now embeds the first live replay target on restored `docker-runtime`, records per-scenario latency and success-rate data, and falls back to Proxmox guest-agent execution when the restored guest never exposes an SSH banner through the fixture network.
- The 2026-03-27 latest-`origin/main` live replay proved the new harness and fallback path end to end, but the restored `docker-runtime` services themselves remained unhealthy after boot: Keycloak still refused loopback connections, NetBox and Windmill reset their local sockets, and OpenBao stayed sealed with HTTP `503`. Platform version advancement remains blocked until the underlying restore-health gap is resolved.
