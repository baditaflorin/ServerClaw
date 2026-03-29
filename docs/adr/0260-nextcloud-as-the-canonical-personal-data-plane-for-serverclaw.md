# ADR 0260: Nextcloud As The Canonical Personal Data Plane For ServerClaw

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.87
- Implemented In Platform Version: 0.130.59
- Implemented On: 2026-03-29
- Date: 2026-03-28

## Context

ServerClaw needs a durable, user-owned place for personal data such as:

- files and attachments
- calendars
- contacts
- tasks and notes
- agent-generated drafts that should stay under user control

Storing those artifacts only inside vendor connectors or only inside assistant
runtime databases would make portability, privacy, and user ownership weaker.

## Decision

We will use **Nextcloud** as the canonical personal data plane for ServerClaw.

### Data-plane rule

- files and attachments should prefer WebDAV-backed storage in Nextcloud
- calendars and tasks should prefer CalDAV-backed storage
- contacts should prefer CardDAV-backed storage
- user-facing drafts, notes, or assistant-produced documents should prefer
  user-owned Nextcloud locations when durable retention is desired

### Integration rule

- ServerClaw reaches Nextcloud through standard protocols and typed ports
- n8n may sync external systems into or out of Nextcloud where that reduces
  vendor lock-in

## Consequences

**Positive**

- Users get a self-hosted personal-data home instead of a pile of connector-side
  fragments.
- Standard protocols reduce coupling between the assistant runtime and one
  product-specific API shape.
- Personal data can be retained, exported, and governed separately from traces
  or control-plane metadata.

**Negative / Trade-offs**

- Nextcloud adds another important stateful service to secure and recover.
- Some external services will still need direct connectors when their data does
  not map cleanly into files, DAV objects, or notes.

## Boundaries

- Nextcloud is not the canonical store for build artifacts, release bundles, or
  repo source code.
- This ADR does not require every personal datum to be mirrored into Nextcloud,
  but it makes Nextcloud the default durable home when the product controls the
  storage choice.

## Related ADRs

- ADR 0206: Ports and adapters for external integrations
- ADR 0259: n8n as the external app connector fabric for ServerClaw

## References

- <https://docs.nextcloud.com/server/latest/admin_manual/>

## Replaceability Scorecard

- Capability Definition: `personal_data_plane` as defined by ADR 0206 typed integration boundaries, ADR 0259 connector portability expectations, and the Nextcloud runbook.
- Contract Fit: strong for user-owned files, attachments, and DAV-backed calendars, contacts, and tasks behind standard protocols instead of a vendor-specific assistant storage API.
- Data Export / Import: WebDAV tree exports, DAV collections, PostgreSQL metadata backups, and filesystem snapshots can be migrated into another standards-based personal data plane without changing the surrounding repo-managed topology contracts.
- Migration Complexity: medium because user accounts, sync clients, sharing state, background jobs, and large-upload publication settings must move together to avoid data drift or client breakage.
- Proprietary Surface Area: medium because sharing semantics, app settings, and admin workflows are product-shaped even though the durable data stays reachable through portable DAV and filesystem contracts.
- Approved Exceptions: Nextcloud-native admin UI, sharing policy, and application settings are accepted while the repo keeps canonical DNS, runtime topology, secret ownership, and live-apply evidence outside the product.
- Fallback / Downgrade: read-only WebDAV export plus filesystem and PostgreSQL restore on a replacement personal-data plane can preserve durable access while richer sharing and task semantics are rebuilt.
- Observability / Audit Continuity: `status.php` health, OCC verification, shared edge probes, uptime monitoring, and live-apply receipts provide the continuity surface during migration or downgrade.

## Vendor Exit Plan

- Reevaluation Triggers: sustained upstream security concerns, broken DAV interoperability, unacceptable large-upload handling, or an inability to preserve user-owned exports through repo-managed automation.
- Portable Artifacts: WebDAV file trees, DAV objects, PostgreSQL dumps, controller-local bootstrap credentials, health-probe contracts, service topology records, and live-apply receipts.
- Migration Path: stand up the replacement personal-data plane in parallel, export files plus DAV data, replay health and sync smoke checks, cut public DNS and client configuration by wave, then retire Nextcloud after a bounded read-only overlap window.
- Alternative Product: Seafile plus Radicale.
- Owner: platform collaboration.
- Review Cadence: quarterly.
