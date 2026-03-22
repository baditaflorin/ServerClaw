# ADR 0064: Health Probe Contracts For All Services

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Services on this platform are currently considered healthy if:

- their systemd unit is `active (running)`, or
- their Docker container is in the `running` state

Neither check confirms that the service is actually responding correctly. A service can be `running` while its HTTP handler returns 500, its database connection pool is exhausted, or its TLS certificate has expired.

Uptime Kuma (ADR 0027) already performs external HTTP checks for public-facing endpoints, but:

- there is no internal liveness definition for each service
- there is no readiness probe contract for services that gate other services (e.g. postgres, step-ca, OpenBao)
- automated rollouts have no structured signal to determine when a new deployment is safe to proceed
- agents querying "is service X healthy" must infer an answer from logs and metrics rather than a canonical probe

## Decision

We will define a health probe contract for every managed service and enforce it in the Ansible role for that service.

Contract structure per service (documented in `docs/runbooks/health-probe-contracts.md`):

1. **liveness** — a minimal check that the process is alive and responding (e.g. TCP connect or `GET /healthz`)
2. **readiness** — a deeper check confirming the service can handle real traffic (e.g. `GET /readyz` with dependency checks, or a SQL ping for postgres)
3. **probe timeout and retry** — maximum wait and retry interval used by Ansible `wait_for` or `uri` tasks during role convergence
4. **Uptime Kuma entry** — whether the service should be listed in `config/uptime-kuma/` and at what interval

Implementation:

- each service role gains a `tasks/verify.yml` that runs the liveness and readiness probes after convergence
- the `make validate` gate runs a syntax check of every `verify.yml` to catch broken probe definitions before live apply
- a new `config/health-probe-catalog.json` lists every service with its probe URL, method, expected status code, and timeout — machine-readable for agents and automation

## Consequences

- Convergence runs fail loudly if a service does not become healthy within the declared timeout, rather than succeeding silently and leaving a broken service.
- Agents can use `health-probe-catalog.json` to query the live state of any service without guessing.
- Each service role owner must keep the probe contract current when deployment details change.
- Services without a natural HTTP health endpoint must document their liveness mechanism explicitly.

## Boundaries

- Probe definitions are functional contracts, not SLA commitments; alerting thresholds live in Grafana.
- Health probes do not replace full integration tests; they are lightweight convergence checks only.
- External health checks via Uptime Kuma complement but do not replace internal readiness probes.
