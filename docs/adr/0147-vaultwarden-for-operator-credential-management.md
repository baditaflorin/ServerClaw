# ADR 0147: Vaultwarden for Operator Credential Management

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.147.0
- Implemented In Platform Version: 0.130.12
- Implemented On: 2026-03-26
- Date: 2026-03-24

## Context

The platform manages infrastructure secrets well: OpenBao (ADR 0043) stores API tokens, database passwords, and service credentials with short TTLs and audit logs. However, there is a category of credentials that OpenBao is not designed for: **human-operated credentials** — passwords for web UIs, recovery codes for TOTP, API keys for external services the operator uses, and notes about access procedures for out-of-band systems.

Currently these operator credentials live in:

- The operator's personal password manager (e.g., 1Password, Bitwarden, KeePass).
- Informal notes in the operator's `~/.ssh/config`, `~/.netrc`, or local files.
- The platform documentation (runbooks that include example credentials or setup codes).
- The operator's brain.

The gap is that there is no **platform-owned** store for operator credentials. When an operator's personal machine is unavailable (loss, theft, hardware failure), there is no path to recover access to external services like the Hetzner API key, the domain registrar login, or the DNS provider credentials — all of which are needed for break-glass recovery procedures.

**Vaultwarden** is a self-hosted, open-source, Bitwarden-compatible credential vault. It provides:
- A web UI and browser extension (the standard Bitwarden extension) for operators.
- An administrative API compatible with the Bitwarden CLI (`bw`).
- Organisation and collection support for shared team credentials.
- TOTP management (replacing separate TOTP apps for platform-related accounts).
- Secure notes for recovery codes and out-of-band access procedures.

This complements OpenBao: OpenBao manages machine-readable infrastructure secrets; Vaultwarden manages human-operated credentials and out-of-band access information.

## Decision

We will deploy **Vaultwarden** on `docker-runtime-lv3` as a Bitwarden-compatible self-hosted credential vault for operator use.

### Deployment

Vaultwarden is now repo-managed on `docker-runtime-lv3` with:

- a PostgreSQL backend on `postgres-lv3`
- a private HTTPS listener on `10.10.10.20:8222`
- a Tailscale-published controller URL at `https://vault.lv3.org`
- a `step-ca` issued internal TLS certificate renewed by a managed systemd timer
- a controller-local admin token artifact for the bounded admin API bootstrap path

Vaultwarden's admin and user surfaces are restricted to Tailscale-only access. No public internet publication is allowed.

### Organisation structure

A single Vaultwarden organisation "LV3 Platform" with two collections:

| Collection | Contents | Access |
|---|---|---|
| `platform-recovery` | Break-glass passwords, TOTP recovery codes, Hetzner API key, domain registrar, DNS provider, physical access codes | All platform operators |
| `platform-services` | Credentials for services not managed by OpenBao (e.g., external SaaS logins, vendor portals) | All platform operators |
| `personal` | Individual operator credentials (managed by each operator personally) | Per-operator only |

The current implementation bootstraps the private Vaultwarden service, invites `ops@lv3.org`, and reserves organisation creation to that named operator account so the shared vault can be initialized without opening anonymous signups.

### TOTP migration

Platform-related TOTP accounts (Proxmox admin TOTP, Keycloak admin TOTP, break-glass TOTP) are migrated to Vaultwarden's built-in TOTP manager. This consolidates authentication factors in the same tool as the passwords, reducing the number of devices required for break-glass access.

### Bitwarden CLI integration

The Bitwarden CLI (`bw`) is available to the operator path for controlled exports and future CI lookups against credentials that are intentionally stored in Vaultwarden rather than OpenBao.

### Backup

Vaultwarden's Postgres database is backed up by the platform's standard PBS backup policy (ADR 0029). The backup is encrypted at rest. An additional export to an encrypted file (using `bw export --format encrypted_json`) is stored offline quarterly as a break-glass offline backup for the break-glass credential collection.

### Platform API for agents

Vaultwarden's REST API is available only for tightly scoped future automation. This implementation does not expose broad agent enumeration or search across the vault; any later agent path must remain collection-scoped and explicitly documented.

## Consequences

**Positive**

- Platform recovery credentials (break-glass passwords, TOTP recovery codes, external service API keys) now have a single private, backed-up, access-controlled home.
- Loss of an operator's personal machine no longer blocks recovery of platform-owned shared credentials once the named operator vault is initialized.
- The standard Bitwarden browser extension can target the private service with the trusted LV3 internal CA root.

**Negative / Trade-offs**

- Vaultwarden is a high-value target: it contains the break-glass credentials. It must remain private-only, regularly backed up, and protected by a strong operator master password.
- Operators must trust the LV3 internal CA root certificate on their client device because `vault.lv3.org` is intentionally served with an internal `step-ca` certificate rather than a public CA certificate.
- The initial organisation and collection creation still requires the invited named operator to complete first login and finish the shared-vault setup.

## Boundaries

- Vaultwarden stores human-operated credentials. Infrastructure secrets (database passwords, API tokens managed by OpenBao) are not duplicated in Vaultwarden as the source of truth.
- Vaultwarden stays private-only on the Tailscale path and is not published through the public NGINX edge.
- The admin token is a bootstrap control only; it is not a substitute for routine operator login.

## Related ADRs

- ADR 0029: PBS backup (Vaultwarden database backup policy)
- ADR 0042: step-ca for internal TLS on private operator services
- ADR 0043: OpenBao (infrastructure secrets; separate from operator credentials)
- ADR 0051: Break-glass and recovery (platform-recovery collection covers break-glass credentials)
- ADR 0056: Keycloak SSO (Keycloak admin TOTP migrated to Vaultwarden)
- ADR 0125: Agent capability bounds (future agent access restricted to designated collection)
