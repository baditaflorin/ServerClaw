# ADR 0233: Signed Release Bundles Via Gitea Releases And Cosign

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.54
- Implemented In Platform Version: 0.130.43
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

If the server is going to reconcile itself, it needs execution inputs that are
more deliberate than "whatever mutable checkout happened to be open in the chat
client".

Raw git refs are useful, but production-ready server-side operation also wants:

- immutable release inputs
- provenance and verification
- a durable fetch surface inside the platform boundary
- a clean separation between authoring branches and consumable runtime bundles

## Decision

We will package server-consumable control inputs as **signed release bundles**
stored in **Gitea Releases or Packages** and verified with **Cosign**.

### Bundle contents

Release bundles may contain:

- validated playbooks and supporting config
- policy bundles
- generated manifests
- runbook metadata
- other machine-consumable control artifacts needed by server-side reconcile
  paths

### Verification rule

- bundles must be signed before the server treats them as eligible runtime input
- server-side consumers verify bundle integrity and identity before execution
- mutable workstation checkouts are never treated as the production deployment
  artifact

### Role in the control model

- Gitea remains the authoritative local release distribution surface
- Cosign provides artifact signing and verification
- `ansible-pull`, Windmill, and future Nomad jobs may consume a verified release
  bundle instead of a mutable live checkout when stronger execution provenance is
  needed

## Consequences

**Positive**

- The server can act on verified, immutable inputs.
- Release preparation becomes a first-class production concern instead of an
  incidental git operation.
- Provenance improves for later audits and recovery drills.

**Negative / Trade-offs**

- Bundle design and signing policy add another release step.
- Operators must manage both source refs and bundled execution inputs.

## Boundaries

- This ADR does not replace git as the design source of truth.
- Signed bundles complement runtime execution; they do not remove the need for
  approval gates, policy checks, or recovery planning.

## Related ADRs

- ADR 0143: Gitea for self-hosted git and CI
- ADR 0168: Automated validation gate
- ADR 0224: Server-resident operations as the default control model
- ADR 0225: Server-resident reconciliation via Ansible Pull
- ADR 0229: Gitea Actions runners for on-platform validation and release
  preparation
