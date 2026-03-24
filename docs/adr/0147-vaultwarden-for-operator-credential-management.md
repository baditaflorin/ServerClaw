# ADR 0147: Vaultwarden for Operator Credential Management

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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

```yaml
# In versions/stack.yaml
- service: vaultwarden
  vm: docker-runtime-lv3
  image: vaultwarden/server:latest
  port: 8888
  access: tailscale_only          # Never publicly accessible
  data_volume: /data/vaultwarden
  database: postgres-lv3          # Postgres backend (not SQLite, for reliability)
  subdomain: vault.lv3.org        # Tailscale-only; not published to public internet
```

Vaultwarden's admin panel is restricted to Tailscale-only access. No public internet exposure.

### Organisation structure

A single Vaultwarden organisation "LV3 Platform" with two collections:

| Collection | Contents | Access |
|---|---|---|
| `platform-recovery` | Break-glass passwords, TOTP recovery codes, Hetzner API key, domain registrar, DNS provider, physical access codes | All platform operators |
| `platform-services` | Credentials for services not managed by OpenBao (e.g., external SaaS logins, vendor portals) | All platform operators |
| `personal` | Individual operator credentials (managed by each operator personally) | Per-operator only |

### TOTP migration

Platform-related TOTP accounts (Proxmox admin TOTP, Keycloak admin TOTP, break-glass TOTP) are migrated to Vaultwarden's built-in TOTP manager. This consolidates authentication factors in the same tool as the passwords, reducing the number of devices required for break-glass access.

### Bitwarden CLI integration

The Bitwarden CLI (`bw`) is available in the platform's Docker build environment for CI automation that needs to look up credentials:

```bash
# In a Gitea Actions workflow (ADR 0143) that needs an external API key
BW_SESSION=$(bw unlock --passwordenv BW_MASTER_PASSWORD)
HETZNER_API_KEY=$(bw get password "Hetzner API Token" --session $BW_SESSION)
```

This is preferable to storing external API keys in Gitea secrets (which are less auditable) or in OpenBao (which is designed for infrastructure secrets, not human credentials).

### Backup

Vaultwarden's Postgres database is backed up by the platform's standard PBS backup policy (ADR 0029). The backup is encrypted at rest. An additional export to an encrypted file (using `bw export --format encrypted_json`) is stored offline quarterly as a break-glass offline backup for the break-glass credential collection.

### Platform API for agents

The Bitwarden REST API exposed by Vaultwarden is available to platform agents for specific, scoped reads:

```python
# Only for credentials explicitly shared to the 'agent' collection
vw = VaultwardenClient(base_url="http://vaultwarden:8888", token=openbao.get("vaultwarden/agent-token"))
recovery_code = vw.get_item("keycloak-admin-recovery-codes")
```

Agent access is limited to a dedicated `agent` collection. Agents cannot enumerate or search all collections; they can only read items by exact name within their collection. This is appropriate for runbook automation scenarios where a recovery code is needed (e.g., the Keycloak TOTP recovery runbook).

## Consequences

**Positive**

- Platform recovery credentials (break-glass passwords, TOTP recovery codes, external service API keys) have a single, backed-up, access-controlled home. Loss of an operator's personal machine no longer blocks platform recovery.
- TOTP consolidation reduces the number of devices required for break-glass access.
- The standard Bitwarden browser extension works with Vaultwarden; no new client software is needed for operators who already use Bitwarden.

**Negative / Trade-offs**

- Vaultwarden is a high-value target: it contains the break-glass credentials. It must be protected with the highest available controls (Tailscale-only access, regular backups, strong master password policy). A compromise of Vaultwarden is effectively a full platform compromise.
- The master password for the Vaultwarden organisation account is the ultimate break-glass credential; it must be stored offline (in the platform's physical break-glass envelope) since it cannot be recovered via Vaultwarden itself.
- Vaultwarden uses the unofficial Bitwarden protocol. It is functionally compatible but may lag behind official Bitwarden server features or break on Bitwarden client updates.

## Boundaries

- Vaultwarden stores human-operated credentials. Infrastructure secrets (database passwords, API tokens managed by OpenBao) are not duplicated in Vaultwarden. The two stores are complementary, not overlapping.
- Vaultwarden's agent access is limited to explicitly designated items. Agents cannot read all vault contents.

## Related ADRs

- ADR 0029: PBS backup (Vaultwarden database backup policy)
- ADR 0043: OpenBao (infrastructure secrets; separate from operator credentials)
- ADR 0051: Break-glass and recovery (platform-recovery collection covers break-glass credentials)
- ADR 0056: Keycloak SSO (Keycloak admin TOTP migrated to Vaultwarden)
- ADR 0125: Agent capability bounds (agent access restricted to designated collection)
- ADR 0143: Gitea CI (bw CLI for CI secrets lookup)
