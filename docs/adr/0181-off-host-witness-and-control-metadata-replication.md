# ADR 0181: Off-Host Witness and Control Metadata Replication

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-26

## Context

As long as there is only one Hetzner host, the whole platform has a hard physical single point of failure. The best immediate redundancy improvement is to ensure the control metadata required to recover or continue operating is available off-host.

That metadata includes more than VM backups. It includes:

- git repository truth
- release and receipt history
- inventory and generated configuration contracts
- backup catalogs and restore pointers
- DNS, PKI, and secret bootstrap metadata

Without an off-host witness, recovery depends on the failed host still being readable or on operator memory.

## Decision

We will maintain **off-host replicated control metadata** in at least two independent locations outside the primary Proxmox host.

### Minimum witness bundle

The witness bundle must include:

- repository mirror or immutable release archive
- `workstreams.yaml`, ADRs, runbooks, and receipts
- versions and promotion metadata
- backup inventory and restore instructions
- secret recovery metadata sufficient to locate, not expose, secret material

### Replication targets

At least two independent targets are required, for example:

- GitHub or another git remote
- object storage archive

### Verification

Replication is not considered healthy unless a periodic drill proves the witness bundle can bootstrap a recovery workflow without consulting the failed host.

## Consequences

**Positive**

- Recovery no longer depends on local disk survival alone.
- Parallel operators and agents can rely on an external source of durable coordination truth.
- Redundancy improves immediately without waiting for a second compute host.

**Negative / Trade-offs**

- Witness bundles must be curated carefully to avoid leaking secrets.
- Replication health becomes another thing to monitor and test.

## Boundaries

- This ADR covers control metadata, not full runtime service availability.
- Off-host metadata does not eliminate the need for PBS backups and restore verification.

## Related ADRs

- ADR 0036: Live-apply receipts
- ADR 0051: Control-plane backup recovery and break-glass
- ADR 0099: Automated backup restore verification
- ADR 0179: Service redundancy tier matrix
