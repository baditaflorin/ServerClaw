# ADR 0146: Langfuse For Agent Observability

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.163.0
- Implemented In Platform Version: 0.130.14
- Implemented On: 2026-03-26
- Date: 2026-03-24

## Context

The platform now has several repo-managed agent and LLM-adjacent surfaces, but it still lacks one self-hosted trace system dedicated to LLM application observability. Grafana Tempo covers platform traces, not agent-specific prompt, generation, score, and feedback workflows. Open WebUI provides an operator-facing workbench, but it is not the system of record for agent traces or evaluation.

The missing capability is:

1. one repo-managed Langfuse deployment on the existing Docker runtime
2. one durable bootstrap project and API key pair for approved agent telemetry
3. one repeatable smoke path that proves traces are ingested and reachable in the Langfuse UI

## Decision

We will deploy **self-hosted Langfuse** on `docker-runtime-lv3` and publish it at `https://langfuse.lv3.org`.

### Runtime shape

The repo-managed runtime will use:

- `docker-runtime-lv3` for `langfuse-web`, `langfuse-worker`, ClickHouse, Redis, and MinIO
- `postgres-lv3` for the PostgreSQL application database
- the shared NGINX edge for the public web hostname

### Identity and access

Langfuse will keep a repo-managed bootstrap credentials user for break-glass and automated UI verification.

Routine interactive access will also be wired through the shared Keycloak realm by provisioning a dedicated confidential OIDC client for Langfuse. Public sign-up remains disabled.

### Bootstrap contract

The repo will seed:

- one organization: `lv3`
- one project: `lv3-agent-observability`
- one repo-managed project public key
- one repo-managed project secret key

This makes Langfuse immediately usable by future repo-managed agent runtimes without manual UI bootstrapping.

### Verification contract

The implementation must prove:

1. the Langfuse runtime is healthy
2. the seeded project is reachable through the public API
3. one synthetic trace is ingested successfully
4. one direct Langfuse UI trace URL resolves for the repo-managed bootstrap user

## Consequences

**Positive**

- agent traces, generations, and scores gain a dedicated self-hosted system of record
- future agent runtimes can adopt one repo-managed API key contract instead of ad hoc trace backends
- the platform gets a repeatable live verification path for LLM telemetry, not only service health

**Negative / Trade-offs**

- Langfuse introduces new operational state in ClickHouse, Redis, and MinIO on `docker-runtime-lv3`
- media-upload ergonomics remain intentionally conservative because the service is published without a separate public object-store endpoint
- the Langfuse runtime depends on both Keycloak and PostgreSQL availability for the full operator experience

## Boundaries

- This ADR does not move platform service traces from Grafana Tempo to Langfuse.
- This ADR does not treat Langfuse as a public anonymous surface.
- This ADR does not require every existing repo workflow to emit Langfuse traces immediately.

## Related ADRs

- ADR 0043: OpenBao for secrets, transit, and dynamic credentials
- ADR 0053: OpenTelemetry traces and service maps with Grafana Tempo
- ADR 0056: Keycloak for operator and agent SSO
- ADR 0077: Compose runtime secrets injection
