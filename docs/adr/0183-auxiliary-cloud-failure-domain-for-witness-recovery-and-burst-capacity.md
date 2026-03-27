# ADR 0183: Auxiliary Cloud Failure Domain for Witness, Recovery, and Burst Capacity

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-27

## Context

The current platform runs on a single Hetzner dedicated server. ADR 0179 and ADR 0180 already make the key limitation explicit: same-host standbys help with guest or operator faults, but they do not provide honest protection from host loss.

At the same time, the platform now wants three things that compete for the same local resources:

- off-host quorum and control metadata
- restore and failover rehearsals in isolated environments
- short-lived burst capacity for branch previews and test fixtures

Keeping all three on the same dedicated host weakens the HA story and turns testing into a zero-sum fight against production headroom.

## Decision

We will add a small **auxiliary cloud failure domain** using Hetzner Cloud for non-primary control-plane resilience and burstable ephemeral workloads.

### Intended uses

The auxiliary cloud domain may host:

- quorum witnesses and control-plane coordinators
- off-host release receipts and orchestration metadata replicas
- branch preview environments
- restore rehearsal targets
- prewarmed ephemeral fixture pools

It must not host the sole primary copy of any stateful production service.

### Connectivity model

The auxiliary domain joins the private management plane over a repo-managed overlay network such as Tailscale or WireGuard. All cross-domain access must use named non-root identities and the same machine-readable inventories used for the dedicated host.

### HA honesty rule

A service may not claim an implemented redundancy posture above same-host recovery unless at least one required recovery function lives in the auxiliary cloud domain or another distinct failure domain.

Examples:

- off-host witness for leader election
- restore controller that survives host loss
- preview or drill environment that can continue when the dedicated host is degraded

### Capacity role

The auxiliary domain is the default spillover target for preview and rehearsal workloads when local burst capacity is exhausted. Production standby reservations on the dedicated host must not be consumed for convenience test workloads when cloud burst capacity is available.

## Consequences

**Positive**

- The platform gains a real second failure domain without immediately committing to a second dedicated server.
- Test and preview workloads stop competing as directly with standby headroom on the Proxmox host.
- Control and recovery workflows can keep operating during partial dedicated-host outages.

**Negative / Trade-offs**

- This adds another network boundary, another inventory slice, and another set of credentials to manage.
- Hetzner Cloud is a separate failure domain from the dedicated host, but not from the provider itself; this is not a full multi-provider strategy.
- Operators must be disciplined about keeping production primaries off the burst environment unless an explicit future ADR changes that rule.

## Boundaries

- This ADR establishes the auxiliary domain role; it does not itself choose which services replicate there.
- This ADR does not declare the platform fully HA across host loss; it creates the minimum off-host foundation for future ADRs to do so honestly.

## Related ADRs

- ADR 0100: Formal RTO/RPO targets and disaster recovery playbook
- ADR 0179: Service redundancy tier matrix
- ADR 0180: Standby capacity reservation and placement rules
- ADR 0181: Off-host witness and control metadata replication
