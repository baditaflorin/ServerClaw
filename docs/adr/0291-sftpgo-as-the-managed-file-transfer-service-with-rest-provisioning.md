# ADR 0291: SFTPGo As The Managed File Transfer Service With REST Provisioning

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

Several platform workflows require secure file transfer over SFTP or WebDAV:

- external partners delivering data files to the platform's ingestion
  pipeline (e.g. CSV exports, EDI files, document bundles)
- automated export of platform artefacts to partners who cannot consume
  an S3-compatible API
- backup agents on legacy systems that speak only SFTP

At present, SFTP access is provided by the host OpenSSH daemon with shared
system accounts. This creates two problems:

- provisioning a new SFTP user or restricting their home directory requires
  SSH access to the host and manual `useradd` / `chroot` commands—an
  awkward shell session that must be performed by a human and leaves no
  structured audit trail
- there is no API to query who has access, what their quota is, or when
  they last connected; this information lives in `/etc/passwd` and SSH
  auth logs and is not queryable programmatically

SFTPGo is a CPU-only, open-source file transfer server that supports SFTP,
WebDAV, FTP/S, and an HTTP REST API. Every management operation—user
creation, virtual filesystem mapping, quota setting, key management, and
connection monitoring—is available via the REST API with a published OpenAPI
specification. The system OpenSSH daemon is not involved; SFTPGo manages its
own user database backed by PostgreSQL.

## Decision

We will deploy **SFTPGo** as the managed file transfer service for all SFTP,
WebDAV, and file-drop workflows.

### Deployment rules

- SFTPGo runs as a Docker Compose service on the docker-runtime VM using
  the official `drakkan/sftpgo` image
- It is internal-only for admin; the SFTP and WebDAV endpoints are published
  through the NGINX edge on dedicated ports or subdomains
- SFTPGo listens on:
  - `2022/tcp` — SFTP (mapped to the host's external SFTP port)
  - `8090/tcp` — WebDAV (proxied through NGINX)
  - `8080/tcp` — Admin REST API and web UI (internal network only)
- SFTPGo uses the shared PostgreSQL cluster (ADR 0042) with a dedicated
  `sftpgo` database for the user registry and event log
- Virtual home directories are mapped onto a named Docker volume that is
  included in the backup scope (ADR 0086)
- Secrets (database password, admin API key, OIDC client credentials) are
  injected from OpenBao following ADR 0077

### API-first provisioning rules

- SFTP users are created and managed exclusively via the SFTPGo REST API
  (`POST /api/v2/users`); manual database entries and SSH system account
  creation are prohibited
- The Ansible role includes a `seed_users` task that calls the SFTPGo API
  to create the standard service accounts declared in `defaults/main.yml`;
  this is idempotent and is the canonical record for who has SFTP access
- SSH public keys for SFTP users are stored in OpenBao and written to
  SFTPGo via the API key management endpoint on every Ansible converge;
  keys are never stored outside OpenBao and SFTPGo's database
- Quota limits (max upload size, max number of files) are set per user
  via the API; they are not enforced at the filesystem level
- Connection events (login, upload, download, logout) are pushed to NATS
  JetStream (ADR 0276) via the SFTPGo event hook; downstream consumers
  can audit file transfer activity without querying the database

### Virtual filesystem rules

- each SFTP user is restricted to a virtual root that maps to a specific
  sub-path of the data volume or to a MinIO bucket (ADR 0274) via the
  S3 backend; users cannot traverse above their virtual root
- MinIO-backed virtual filesystems are preferred for partner-facing
  accounts; they allow files delivered via SFTP to be immediately
  available to MinIO-native workflows without a copy step

## Consequences

**Positive**

- Provisioning a new SFTP user is a single REST API call that can be
  triggered from a Windmill onboarding workflow; no SSH session or manual
  host configuration is needed.
- The audit log of connections and transfers is a queryable REST API and
  an event stream on NATS; compliance reporting does not require parsing
  SSH auth logs.
- The MinIO-backed virtual filesystem bridges SFTP delivery with the
  object storage layer; files arrive via SFTP and are immediately
  addressable as S3 objects.
- SFTPGo's WebDAV support allows the same user accounts to be accessed
  from Windows Explorer or macOS Finder without additional software.

**Negative / Trade-offs**

- SFTPGo runs on a non-standard SFTP port (2022); external partners must
  be informed of the port, and any firewall rules must allow it explicitly.
- The system OpenSSH daemon's SFTP subsystem must be disabled for the
  same port to avoid conflicts; this is a host-level change that must be
  coordinated with the Ansible host role.

## Boundaries

- SFTPGo handles file transfer over SFTP, WebDAV, and FTP; it does not
  replace MinIO (ADR 0274) as the primary object storage layer for
  platform-internal workflows.
- SFTPGo user accounts are scoped to file transfer; they are not platform
  identity accounts and do not grant access to any other service.
- The SFTPGo web UI is available for diagnostic inspection; user management
  performed through the UI is treated as drift and reconciled on the next
  Ansible converge.

## Related ADRs

- ADR 0042: PostgreSQL as the shared relational database
- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0276: NATS JetStream as the platform event bus

## References

- <https://sftpgo.com/docs/api/>
- <https://github.com/drakkan/sftpgo/blob/main/openapi/openapi.yaml>
