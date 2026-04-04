# ADR 0346: Compose Dependency Health Gates As A Repo-Enforced Resilience Baseline

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.4
- Implemented In Platform Version: 0.130.98
- Implemented On: 2026-04-04
- Date: 2026-04-04
- Tags: compose, docker, readiness, resilience, validation

## Context

The repository already models service health, SLOs, correction loops, and
recovery policy, but some compose-managed services still rely on blind startup
ordering:

- `depends_on` entries with no health condition
- `condition: service_started` for dependencies that still need bounded
  readiness before downstream services can start safely
- no repo-level validation that catches those race conditions before they
  reach a live replay

That gap makes recovery noisy and unpredictable. A service can pass a broad
platform health model while still starting too early during boot, replay, or
repair. On a shared runtime pool, those races are especially expensive because
one flapping dependency can make unrelated service replays look broken.

## Decision

We will treat **health-gated compose dependencies** as a repository resilience
baseline.

### Required rule

For compose-managed services:

- if a runtime template declares no local `depends_on`, no extra dependency gate
  is required
- if a runtime template declares local `depends_on`, the template must include a
  governed `condition: service_healthy` startup gate somewhere in that local
  dependency contract
- if an upstream image or dependency cannot yet expose a safe in-container
  health probe, the owning service must carry a time-bounded suppression in
  `config/service-completeness.json` and a documented follow-up path

### Enforcement path

- `scripts/service_completeness.py` becomes the repo gate for this invariant
- compose roles should prefer narrow, dependency-local health probes such as:
  - an OpenBao-rendered env file existing and being non-empty
  - a sidecar or cache CLI returning a local ready response
  - a service's built-in health subcommand when the container already ships it

## Consequences

**Positive**

- startup and recovery ordering becomes reviewable repository truth
- more replay failures surface as explicit contract violations instead of
  intermittent races
- resilience debt stays visible through time-bounded suppressions rather than
  hidden in role templates

**Negative / Trade-offs**

- some third-party images still do not give us a safe built-in health probe, so
  short-lived suppressions are still needed
- role authors now have to think about dependency readiness, not just container
  creation order

## Boundaries

- This ADR governs compose dependency readiness in repo-managed runtime roles.
- It does not replace higher-level service health probes, SLOs, or disaster
  recovery policy.
- It does not require every dependency to use the exact same probe mechanism;
  the probe only needs to be safe, local, and reviewable in the repo.

## Related ADRs

- ADR 0064: Health probe contracts for all services
- ADR 0107: Platform extension model
- ADR 0204: Self-correcting automation loops
- ADR 0246: Startup, readiness, liveness, and degraded-state semantics
- ADR 0319: Runtime pools as the service partition boundary
