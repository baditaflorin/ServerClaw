# ADR 0229: Gitea Actions Runners For On-Platform Validation And Release Preparation

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-28

## Context

ADR 0143 already established Gitea as the self-hosted git authority, but
production-ready server-resident operation also needs server-side execution for:

- merge validation
- release preparation
- artifact assembly
- packaging or attestations that should not depend on the authoring client

Leaving that work on the laptop keeps too much operational gravity outside the
platform.

## Decision

We will use **Gitea Actions runners (`act_runner`) as the default on-platform
CI and release-preparation workers**.

### Intended responsibilities

- run validation and packaging jobs on merged or proposed refs
- prepare release bundles and machine-consumable artifacts for downstream
  reconcile loops
- execute policy checks that should run server-side even when local checks were
  skipped

### Runtime policy

- runner placement defaults to build-oriented or automation-oriented nodes, not
  control-plane state nodes
- repository and organization scopes must be explicit
- Docker-backed runner mode is preferred over unrestricted host mode unless a
  repo-managed justification exists

## Consequences

**Positive**

- CI and packaging work can happen inside the platform boundary.
- Release preparation no longer depends on the Codex app or a workstation being
  online.
- Validation evidence becomes easier to attach to later server-side reconciliation.

**Negative / Trade-offs**

- Runners themselves become privileged infrastructure that must be hardened.
- Build-node capacity and isolation matter more once more work moves server-side.

## Boundaries

- Gitea Actions runners prepare and validate; they do not automatically mutate
  production without a separate governed path.
- This ADR does not replace Windmill. It covers CI and release-prep roles that
  are better tied to git events.

## Related ADRs

- ADR 0083: Docker-based check runner images
- ADR 0143: Gitea for self-hosted git and CI
- ADR 0168: Automated validation gate
- ADR 0224: Server-resident operations as the default control model
- ADR 0225: Server-resident reconciliation via Ansible Pull
