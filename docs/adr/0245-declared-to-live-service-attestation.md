# ADR 0245: Declared-To-Live Service Attestation

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.72
- Implemented In Platform Version: 0.130.46
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

The service catalog, subdomain catalog, environment topology, and runtime
receipts together describe what should exist, but that still does not prove a
service is really present in the declared environment and host.

For a large multi-stage estate, “exists” must mean more than “has a YAML
entry”.

## Decision

We will require **declared-to-live service attestation** for every active
service and environment pair.

### Required witness dimensions

- declared runtime host or pool
- observed runtime instance or process identity
- declared endpoint or listener
- observed endpoint or listener proof
- last successful assurance receipt for that stage

### Acceptable witness sources

- systemd unit state and local verify receipts
- Docker or Nomad runtime inspection
- world-state snapshots
- route or listener probes that prove the declared endpoint resolves to the
  declared environment

## Consequences

**Positive**

- catalog truth is backed by runtime evidence instead of hope
- missing or orphaned services become visible quickly
- staging and preview environments can be judged by the same core existence
  rules as production

**Negative / Trade-offs**

- evidence freshness becomes an operational concern
- some services will need adapters to translate product-specific state into one
  common attestation model

## Boundaries

- This ADR proves presence and binding; it does not by itself prove full user
  functionality.
- One witness source is not enough when a service is edge-published; route truth
  must also be proven separately.

## Related ADRs

- ADR 0075: Service capability catalog
- ADR 0113: World-state materializer
- ADR 0214: Production and staging cells as the unit of high availability
- ADR 0244: Runtime assurance matrix per service and environment
