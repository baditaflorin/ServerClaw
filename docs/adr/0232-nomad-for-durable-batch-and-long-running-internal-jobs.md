# ADR 0232: Nomad For Durable Batch And Long-Running Internal Jobs

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: 0.130.41
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

Systemd is the right host-native supervisor, and Windmill is the right
workflow-first surface, but some future platform work will need a middle layer
for:

- durable batch jobs that outgrow one host
- long-running internal services that need placement and restart policy
- periodic jobs that should survive beyond one node's local timer state
- operations workloads that are too infrastructure-aware for Windmill but too
  dynamic for static systemd units

Kubernetes would overshoot the current platform shape and operational budget for
those roles.

## Decision

We will adopt **Nomad** as the future distributed scheduler for internal jobs
that outgrow systemd and Windmill.

### Intended use

Nomad is the target runtime for:

- internal long-running control-plane helpers
- build, batch, and replay workloads
- placement-aware recovery and drill jobs
- multi-node internal services that benefit from declarative job specs

### Non-goals

Nomad is not the immediate replacement for:

- Proxmox as the VM substrate
- Docker Compose for every current application stack
- Windmill for browser-first approvals and workflow history

## Consequences

**Positive**

- The platform gains a production-tested scheduler without adopting the full
  Kubernetes stack.
- Job specs can stay repository-managed and placement-aware.
- More roles can move from chat sessions into durable infrastructure.

**Negative / Trade-offs**

- Nomad introduces another critical control-plane component.
- Operators must learn another scheduler and its recovery story.

## Boundaries

- This ADR sets the preferred distributed scheduler direction; it does not claim
  the platform needs Nomad immediately for every current service.
- A later ADR should decide the exact control-plane topology and storage backing
  for Nomad if this direction is implemented.

## Related ADRs

- ADR 0044: Windmill for agent and operator workflows
- ADR 0179: Service redundancy tier matrix
- ADR 0184: Failure-domain labels and anti-affinity policy
- ADR 0224: Server-resident operations as the default control model
- ADR 0226: Systemd units, timers, and paths for host-resident control loops
