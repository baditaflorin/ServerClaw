# ADR 0214: Production And Staging Cells As The Unit Of High Availability

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

ADR 0072 established `production` and `staging` as named environments, but
the platform still lacks one operational unit that ties together topology,
replication, failover, and recovery design.

Today it is too easy to talk about HA in fragments:

- a database replica exists on one VM
- a staging hostname exists on the shared edge
- a backup copy exists on another guest
- a recovery drill runs in an auxiliary lane

Those pieces matter, but without a single unit of design they do not tell us
whether production and staging are shaped the same way, whether a failover
claim is local or cross-environment, or which servers belong to the same
operational boundary.

The platform needs one durable answer to "what exactly are we keeping highly
available?" and "what is staging mirroring when we say staging mirrors
production?".

## Decision

We will treat each environment as a **cell**. A cell is the smallest complete
operational unit that can be reasoned about for topology, replication, failover,
and recovery.

### Cell contract

Every environment cell must define these logical planes, even if a small
deployment temporarily collapses several planes onto fewer VMs:

- `bootstrap_plane`: first-access and trust-establishment surfaces
- `control_plane`: identity, secrets, orchestration, and platform coordination
- `state_plane`: authoritative mutable state such as SQL, queues, object stores,
  and secret authorities
- `workload_plane`: application runtimes and internal worker services
- `edge_plane`: ingress, reverse proxies, and public or partner entrypoints
- `observability_plane`: metrics, logs, traces, alerting, and health reporting
- `recovery_plane`: backup targets, restore controllers, replicas, and drill
  lanes

### Production and staging rule

`production` and `staging` are separate cells, not just different DNS labels.

- Staging must mirror the **shape** of production for the services it validates.
- Staging may run on smaller capacity or collapsed planes, but it must still
  declare the same logical planes explicitly.
- Shared physical infrastructure is allowed only when the shared surface is
  called out as technical debt or capacity optimization rather than silent
  truth.

### HA truth rule

An HA claim must name the cell boundary it protects:

- `intra-cell HA`: protects against process, VM, or local service failure inside
  one environment cell
- `cross-cell replication`: copies data or configuration between cells
- `cross-domain recovery`: survives loss of one failure domain by using another

We will no longer use "high availability" as a blanket phrase without naming
which of those three meanings is intended.

## Consequences

**Positive**

- Production and staging topology become comparable in a governed way.
- Replication and failover discussions gain one stable unit of design.
- Future automation can derive environment intent from cells instead of from
  hostnames and one-off playbook comments.

**Negative / Trade-offs**

- The repository must model more topology metadata up front.
- The current single-host staging story will now appear honestly as a collapsed
  cell, not as a fully independent estate.

## Boundaries

- This ADR defines the architectural unit for HA and staging symmetry; it does
  not itself provision new nodes.
- A cell may still contain same-host components on the current platform; this
  ADR changes the vocabulary and contract, not current hardware limits.
- This ADR does not replace ADR 0179 redundancy tiers. It provides the topology
  boundary within which those tiers are evaluated.

## Related ADRs

- ADR 0072: Staging and production environment topology
- ADR 0073: Environment promotion gate and deployment pipeline
- ADR 0179: Service redundancy tier matrix
- ADR 0183: Auxiliary cloud failure domain for witness, recovery, and burst
  capacity
- ADR 0184: Failure-domain labels and anti-affinity policy
