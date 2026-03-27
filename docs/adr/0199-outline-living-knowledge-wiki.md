# ADR 0199: Outline Living Knowledge Wiki

- Status: Accepted
- Implementation Status: Live-applied on workstream branch
- Implemented In Repo Version: not yet
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

The platform now has a large and growing body of operational knowledge in git, but that knowledge remains optimized for repository authors rather than for everyday browsing, search, and guided reuse by operators and future agents.

The missing capability is:

1. one repo-managed knowledge surface that is easier to browse than raw markdown trees
2. one durable synchronization path from repo truth into that knowledge surface
3. one controlled automation identity that can update living collections without interactive UI work

The canonical source of truth must remain in git. The wiki is a published working view, not a replacement for repository history or release-controlled truth files.

## Decision

We will deploy **Outline** on `docker-runtime-lv3` and publish it at `https://wiki.lv3.org`.

### Runtime shape

The repo-managed runtime uses:

- `docker-runtime-lv3` for Outline, Redis, and MinIO-backed S3-compatible attachment storage
- `postgres-lv3` for the Outline application database
- the shared NGINX edge for the public hostname `wiki.lv3.org`

### Identity and access

Outline delegates routine browser sign-in to the shared Keycloak realm through a dedicated confidential OIDC client.

The first successful OIDC sign-in provisions the initial Outline admin. After that bootstrap, the repo maintains one controller-local Outline API token for automation-driven synchronization and agent-authored updates.

### Living collections

The wiki maintains these top-level collections:

- `ADRs`
- `Runbooks`
- `Incident Postmortems`
- `Agent Findings`
- `Architecture`

The canonical markdown remains in git. The repo-managed sync path publishes landing and index documents into Outline so operators and agents can browse the knowledge graph quickly without importing every markdown file as a standalone document.

### Sync contract

The repo adds `scripts/sync_docs_to_outline.py` and wires it into the version-cut path.

On each repo release cut, the sync publishes or refreshes:

- collection landing pages
- ADR and runbook index documents generated from current repo state
- placeholder or curated landing pages for architecture, postmortems, and agent findings

Future agent workflows may also write directly into `Agent Findings` using the repo-managed API token.

### Draft handling

Runbook draft automation targets `Runbooks / Drafts` inside Outline. The initial implementation provisions the collection structure and sync landing pages so future generators have a stable parent location.

## Consequences

**Positive**

- operators get one browsable, searchable knowledge surface at `wiki.lv3.org`
- release automation now refreshes living knowledge views alongside release artifacts
- future agents can publish findings into a governed knowledge collection instead of hidden chat history

**Negative / Trade-offs**

- Outline introduces new runtime state on `docker-runtime-lv3`
- the published wiki depends on Keycloak, Postgres, and the shared edge for the full browser experience
- the initial sync publishes curated landing and index documents rather than mirroring every markdown file as a separate Outline page

## Boundaries

- This ADR does not replace git as the canonical documentation source.
- This ADR does not move shared release truth into Outline.
- This ADR does not require all future agent findings to bypass the repo; only governed API writes are enabled.

## Related ADRs

- ADR 0043: OpenBao for secrets, transit, and dynamic credentials
- ADR 0056: Keycloak for operator and agent SSO
- ADR 0077: Compose runtime secrets injection
- ADR 0107: Platform extension model
- ADR 0139: Subdomain exposure audit and registry
