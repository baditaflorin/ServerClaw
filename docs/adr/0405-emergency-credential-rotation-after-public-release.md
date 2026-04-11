# ADR 0405: Emergency Credential Rotation After Public Release

- Status: Accepted
- Implementation Status: Accepted, implementation in progress
- Implemented In Repo Version: 0.178.103
- Implemented In Platform Version: n/a
- Implemented On: 2026-04-11
- Date: 2026-04-11
- Concern: Security, Platform Integrity
- Depends on: ADR 0065 (Secret Rotation Automation), ADR 0043 (OpenBao), ADR 0141 (API Token Lifecycle)
- Tags: security, secrets, rotation, incident-response, public-release

---

## Context

On 2026-04-11, the platform codebase was published to a public GitHub repository
(`baditaflorin/ServerClaw`) with 3,339 commits of full git history. A preparation
commit scrubbed identity files (`identity.yml`, `operators.yaml`, `hosts.yml`) but:

1. One Keycloak OIDC client secret was committed in plaintext and missed during
   the scrub (`docs/workstreams/ws-0362-semaphore-keycloak-oidc.md:87`)
2. One Semaphore admin password was present in git history
   (deleted `SEMAPHORE-SETUP-QUICK-START.md`)
3. The complete secret management structure is now public: all 249 secret names,
   `.local/` paths, generation methods, rotation workflows, and OpenBao mount
   paths are visible in `config/controller-local-secrets.json` and
   `config/secret-catalog.json`

Although no actual secret **values** were stored in the repository (except the
three noted above), the exposed **structure** means an attacker who obtains any
single credential from another vector (e.g., compromised backup, shoulder
surfing) now knows exactly where it fits in the platform and what it unlocks.

The correct response is a full rotation of all platform-generated credentials so
that even if old values are recovered from git history or other sources, they are
useless.

## Decision

We will perform a **complete programmatic rotation of all 226 platform-generated
credentials** using a tiered, automated approach. This is not a selective rotation
— every secret whose origin is `generated_by_repo` gets a new value.

### Rotation Tiers

| Tier | Scope | Timeline | Method |
|------|-------|----------|--------|
| **T1** | 3 directly exposed secrets (Keycloak OIDC, Semaphore password, Gitea token) | Immediate | Manual rotation + convergence |
| **T2** | Keycloak (14), OpenBao (8), SSH keys (2), Proxmox tokens (2) — high-privilege | Within 4 hours | Script-driven regeneration + convergence |
| **T3** | All remaining 197 service credentials (database passwords, admin passwords, API keys, encryption keys, Redis passwords, etc.) | Within 24 hours | Batch script + per-service convergence |

### Rotation Method

A new script `scripts/emergency_credential_rotation.py` will:

1. Read `config/controller-local-secrets.json` to enumerate all `generated_by_repo` secrets
2. For each secret, generate a new cryptographically random value using the
   appropriate generator (respecting ADR 0403 safe password alphabet)
3. Write the new value to the `.local/` path
4. Log every rotation to a receipt file for audit trail
5. After regeneration, the operator runs `make converge-<service>` to propagate
   each new credential to the live infrastructure

### What This ADR Does NOT Cover

- **External tokens** (17 secrets with `origin: provided_externally`) — these
  must be rotated manually at their respective providers (Hetzner DNS, Tailscale,
  Ansible Galaxy, etc.)
- **Git history rewriting** — decided separately; credential rotation makes
  history rewriting unnecessary from a security standpoint
- **Infrastructure topology exposure** — IPs and domains are not rotatable;
  hardening is handled by firewall and access control review

## Consequences

### Positive
- All 226 platform-generated credentials become unique and unrelated to any
  value recoverable from the public git history
- Forces a validation of every service's credential consumption path
- Establishes a repeatable emergency rotation procedure for future incidents
- Receipt file provides cryptographic proof of rotation timing

### Negative
- Full platform convergence required — brief service interruptions expected
  during container restarts
- Database password rotation requires coordinated PostgreSQL ALTER ROLE +
  service restart
- SSH key rotation requires redeploying public keys to all managed hosts
- Some services may need manual verification after rotation (e.g., Keycloak
  OIDC login flows)

### Risks
- If convergence order is wrong, services may fail to connect to databases
  with old passwords — mitigated by rotating database passwords and
  reconverging the database role before the application role
- OpenBao AppRole secret IDs are single-use; regenerating them requires
  re-seeding — mitigated by the existing `seeded_secrets_and_verification`
  task includes

## Implementation

See:
- `scripts/emergency_credential_rotation.py` — rotation script
- `docs/runbooks/emergency-credential-rotation.md` — operational runbook
- `receipts/credential-rotations/` — audit trail
