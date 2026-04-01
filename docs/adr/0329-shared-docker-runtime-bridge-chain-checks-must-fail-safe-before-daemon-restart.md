# ADR 0329: Shared Docker Runtime Bridge-Chain Checks Must Fail Safe Before Daemon Restart

- Status: Accepted
- Implementation Status: Partial
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: N/A
- Date: 2026-04-01
- Tags: docker, runtime, uptime, automation, safety

## Context

The platform still runs a large share of its repo-managed services on the
shared `docker-runtime-lv3` guest.

On 2026-04-01, a live apply replay for Grist preserved direct evidence that the
shared Docker bridge-chain preflight escalated a missing `DOCKER` /
`DOCKER-FORWARD` check into a host-wide Docker restart:

- `receipts/live-applies/evidence/2026-04-01-ws-0279-grist-mainline-live-apply-r1-0.177.134.txt`
  shows `lv3.platform.common : Restart Docker when required bridge chains are
  missing` at `2026-04-01T16:21:17Z`
- the same replay ran through `linux_guest_firewall` and the shared
  `docker_runtime` prerequisites on `docker-runtime-lv3` just before that
  restart
- later direct inspection from workstream `ws-0325` found many unrelated
  containers exited or restarting, plus follow-on failures in backup,
  housekeeping, and OpenBao-backed workloads

That behavior conflicts with ADR 0270 and ADR 0319:

- ADR 0270 says publication healing should stay targeted rather than defaulting
  to a blanket host reset
- ADR 0319 says shared runtime pools are already oversized failure domains and
  need smaller blast radii, not broader ones

## Decision

Shared Docker bridge-chain preflight checks on a shared runtime pool must
**fail safe before they restart the Docker daemon**.

### Required behavior

- the shared `common.docker_bridge_chains` helper may warm the Docker socket,
  wait briefly for automatic chain recovery, and verify the expected chains
- if the required chains stay missing after that bounded wait, the helper must
  fail the converge rather than restart `docker.service`
- a host-wide Docker restart on a shared runtime pool now requires either:
  - a service-scoped runtime role that has already proven a targeted recovery
    is impossible, or
  - an explicit operator decision through a documented runbook

### Implementation direction

- shared runtime preflight logic should prefer targeted container or compose
  recovery over daemon-wide restarts
- operator-facing runbooks must explain how to confirm bridge-chain loss and
  when a manual Docker restart is justified
- remaining service-specific Docker restart paths on `docker-runtime-lv3`
  should be treated as follow-up hardening work until they respect the same
  blast-radius rule

## Consequences

**Positive**

- one service replay is less likely to knock over unrelated workloads on the
  shared runtime guest
- bridge-chain loss becomes an explicit degraded-state signal instead of a
  silent daemon restart
- receipts and operator decisions become easier to interpret during incident
  review

**Negative / Trade-offs**

- some converges will now fail earlier and require a deliberate operator
  recovery step
- the repo still contains service-specific restart paths that need separate
  follow-up before the whole runtime fully matches this rule

## Boundaries

- This ADR governs shared Docker bridge-chain preflight behavior on shared
  runtime pools such as `docker-runtime-lv3`.
- It does not ban every Docker restart everywhere; host rebuilds, daemon
  configuration changes, and explicitly approved emergency maintenance windows
  remain valid.

## Related ADRs

- ADR 0023: Docker runtime VM baseline
- ADR 0246: Startup, readiness, liveness, and degraded-state semantics
- ADR 0270: Docker publication self-healing and port-programming assertions
- ADR 0319: Runtime pools as the service partition boundary
