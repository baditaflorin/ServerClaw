# ADR 0043: OpenBao For Secrets, Transit, And Dynamic Credentials

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.48.0
- Implemented In Platform Version: 0.24.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The repository already has controller-local secret handling guidance under ADR 0034, but the platform still lacks an internal secrets authority for:

- API keys used by applications and agents
- service credentials that should not live in repo-managed files
- cryptographic operations such as encrypt, decrypt, sign, and verify
- future dynamic or short-lived credentials issued to workloads

As the system becomes more agentic, the risk from static shared secrets rises quickly.

## Decision

We will use OpenBao as the platform secret authority.

Initial responsibilities:

1. store application and automation secrets outside git
2. expose a private HTTP API for secret retrieval and rotation workflows
3. provide Transit for encryption, signing, and other cryptographic operations
4. provide machine-oriented auth methods for services and agents
5. support dynamic credentials where that meaningfully reduces secret lifetime

Initial placement:

- host: `docker-runtime`
- exposure: private-only, never published directly on the public edge
- storage: single-node durable storage with backup coverage under the control-plane recovery policy

Authentication and authorization must be structured around narrow roles:

- named humans
- named agents
- named services
- break-glass operators

## Replaceability Scorecard

- Capability Definition: `platform_secret_authority` as defined by ADR 0034 controller-local secret handling, ADR 0047 short-lived credential policy, and the OpenBao operational runbook.
- Contract Fit: strong for secret storage, transit cryptography, service and agent auth, and the future dynamic-credential path required by the control plane.
- Data Export / Import: secret-path definitions, policy, auth mounts, transit key metadata, audit configuration, and recovery procedures can be exported and recreated on another secret authority even when secret values themselves are reissued instead of copied verbatim.
- Migration Complexity: high because auth methods, policy boundaries, client bootstrap flows, and secret rotation sequences all have to move together without exposing long-lived fallback credentials.
- Proprietary Surface Area: medium because auth mount semantics, transit APIs, and policy language are product-shaped even though the repo keeps secret inventory and rotation intent in platform-owned catalogs.
- Approved Exceptions: OpenBao-native policy and transit semantics are accepted where they reduce blast radius, provided the repo keeps the canonical secret inventory, rotation workflow, and client ownership metadata outside product-specific exports.
- Fallback / Downgrade: bounded controller-local secrets plus step-ca-issued mTLS and manual rotation can preserve minimum operation while a replacement authority is brought up.
- Observability / Audit Continuity: audit devices, mutation audit logs, rotation receipts, and secret inventory reports remain the continuity surface during migration.

## Vendor Exit Plan

- Reevaluation Triggers: unacceptable seal or recovery posture, unsupported auth integrations, audit gaps, or a sustained inability to rotate secrets without downtime.
- Portable Artifacts: path and policy definitions, auth mount inventory, transit key metadata, controller-local bootstrap manifests, rotation runbooks, and audit sinks.
- Migration Path: stand up the replacement authority in parallel, mirror auth and policy boundaries, rotate service credentials and transit consumers by wave, prove the replacement through health and mutation tests, then disable OpenBao after the final credential cutover.
- Alternative Product: HashiCorp Vault.
- Owner: platform security.
- Review Cadence: quarterly.

## Consequences

- Repo-local secret files stop being the long-term operating model for internal services.
- Agents can receive scoped credentials instead of reusing human or global service tokens.
- Cryptographic operations that currently tempt ad hoc shell handling can move behind a controlled API.
- Bootstrap, unseal or recovery handling, and audit review become part of regular platform operations.

## Boundaries

- OpenBao is the default authority for secrets, tokens, and encryption operations.
- `step-ca` remains the default issuer for SSH and internal X.509 certificates.
- OpenBao PKI or SSH engines may be used later only when there is a clear reason not to use the default `step-ca` path.

## Sources

- [What is OpenBao?](https://openbao.org/docs/what-is-openbao/)
- [AppRole auth method](https://openbao.org/docs/auth/approle/)
- [Transit secrets engine](https://openbao.org/docs/secrets/transit/)
- [PKI secrets engine API](https://openbao.org/api-docs/secret/pki/)

## Implementation Notes

- The repo defines a dedicated OpenBao automation surface through [playbooks/openbao.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/openbao.yml), [roles/openbao_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/openbao_runtime), and [roles/openbao_postgres_backend](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/openbao_postgres_backend).
- [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/workflow-catalog.json) exposes `converge-openbao` as the canonical entry point with explicit preflight, validation, and verification metadata.
- [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/config/controller-local-secrets.json) records the controller-local bootstrap artifacts and scoped AppRole outputs used by the OpenBao workflow.
- Operator usage is documented in [docs/runbooks/configure-openbao.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/runbooks/configure-openbao.md).
- OpenBao runs as a two-node Raft HA pair: the primary node on `docker-runtime` (10.10.10.20) and a peer on `runtime-control` (10.10.10.92). Raft replicates all secret data between nodes; each node must still be unsealed independently because Shamir manages the per-node encryption key, not the Raft data layer.
- Unseal is handled by `lv3-openbao-unseal-watcher.service` on each node — a persistent systemd service (type=simple, Restart=always) that streams `docker events` for lv3-openbao container start events and submits the threshold Shamir keys immediately on each container restart. This replaces the earlier oneshot boot-time pattern, which left OpenBao sealed after mid-session container restarts.
- The watcher script is rendered by the `openbao_runtime` role from `templates/openbao-unseal-watcher.sh.j2` with keys baked in from the repo-managed init payload; `no_log: true` prevents key exposure in Ansible output.
- OpenBao is live on both nodes with managed initialization and unseal, scoped `userpass` and `AppRole` identities, seeded controller and mail secrets, Transit verification, verified PostgreSQL dynamic credential issuance against `postgres`, and a `step-ca`-issued external mTLS listener.
