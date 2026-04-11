# ADR 0042: step-ca For SSH And Internal TLS

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.45.0
- Implemented In Platform Version: 0.22.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The platform already has:

- Tailscale-backed private operator access under ADR 0014
- named non-root host and guest administration under ADR 0018
- durable API automation for Proxmox object management

It does not yet have a first-class internal certificate authority for:

- short-lived SSH user certificates for humans and agents
- SSH host certificates for the Proxmox host and guests
- internal X.509 certificates for private APIs and service-to-service mTLS

That gap keeps routine access tied too closely to long-lived SSH keys and ad hoc certificate handling.

## Decision

We will standardize on `step-ca` as the internal certificate authority for LV3.

Initial scope:

1. issue SSH user certificates for named operators and approved automation identities
2. issue SSH host certificates for the Proxmox host and managed guests
3. issue private X.509 certificates for internal HTTPS and mTLS endpoints
4. expose a private CA API reachable only from trusted LV3 networks

Initial placement:

- host: `docker-runtime`
- exposure: private-only, not published on the public edge
- trust bootstrap: repo-documented CA URL and fingerprint, with secrets kept outside git

Provisioners must be separated by identity class:

- humans
- agents
- services
- hosts

## Replaceability Scorecard

- Capability Definition: `internal_trust_authority` as defined by ADR 0046 identity classes, ADR 0047 short-lived credential policy, and the step-ca runbook.
- Contract Fit: strong for short-lived SSH user certificates, SSH host certificates, and internal X.509 issuance behind a private API.
- Data Export / Import: CA configuration, policy, trusted roots, SSH principal mappings, issued certificate inventories, and host trust bundles can be exported and re-established on another CA.
- Migration Complexity: medium because every SSH and TLS consumer must trust both issuers during the transition and then rotate to the new authority without breaking automation.
- Proprietary Surface Area: low because the repo already treats certificates, trust bundles, and principal mappings as platform-owned concepts instead of step-ca-specific schemas.
- Approved Exceptions: ACME-compatible issuance behavior and step-ca admin tooling are accepted so long as the canonical trust inventory and issued-artifact mapping remain portable.
- Fallback / Downgrade: controller-local SSH keys, break-glass root access, and static internal certificates can keep minimum operator access alive while a replacement CA is introduced.
- Observability / Audit Continuity: certificate issuance, renewal, and revocation remain visible through repo-managed logs, trust-distribution automation, and live-apply receipts during migration.

## Vendor Exit Plan

- Reevaluation Triggers: unsupported auth methods, recovery gaps around CA key custody, upgrade dead-ends, or inability to keep SSH and mTLS issuance policy aligned with platform identity rules.
- Portable Artifacts: root and intermediate material, CA policy, SSH principals, host certificate mappings, trusted root bundles, and issuance inventories.
- Migration Path: stand up the replacement CA in parallel, publish its trust roots beside the current ones, reissue host and user credentials by wave, switch default issuance to the replacement, then retire step-ca once all active principals and services validate cleanly.
- Alternative Product: OpenBao PKI or HashiCorp Vault PKI.
- Owner: platform security.
- Review Cadence: quarterly.

## Consequences

- Routine SSH access can move from long-lived keys toward short-lived certificates.
- Internal API publication can reuse one certificate authority instead of per-service self-signed material.
- `sshd` trust on the Proxmox host and guests becomes CA-based rather than key-copy based.
- CA backup, recovery, and root or intermediate key handling become critical control-plane responsibilities.

## Boundaries

- `step-ca` is the default issuer for SSH and internal X.509 certificates.
- It is not the source of truth for arbitrary application secrets or API passwords.
- Public HTTPS certificates for internet-facing services still follow the existing Let's Encrypt edge model unless a future ADR replaces it.

## Sources

- [step-ca Certificate Authority Overview](https://smallstep.com/docs/step-ca)
- [Getting Started with step-ca](https://smallstep.com/docs/step-ca/getting-started/)
- [Basic Certificate Authority Operations](https://smallstep.com/docs/step-ca/basic-certificate-authority-operations)

## Implementation Notes

- The repo now defines a dedicated `step-ca` automation surface through [playbooks/step-ca.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/step-ca.yml), [roles/step_ca_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/step_ca_runtime), and [roles/step_ca_ssh_trust](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/step_ca_ssh_trust).
- [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/workflow-catalog.json) now exposes `converge-step-ca` as the canonical entry point with explicit preflight, validation, and verification metadata.
- [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/controller-local-secrets.json) now records the controller-local secret material generated and consumed by the `step-ca` workflow.
- Operator usage is documented in [docs/runbooks/configure-step-ca.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/configure-step-ca.md).
- Live application was completed from `main` on 2026-03-22, including proxied CA health verification, short-lived SSH certificate login for `ops`, and private X.509 issuance through the Tailscale-published controller URL.
