# Release 0.178.18

- Date: 2026-04-06

## Summary
- Operational fixes: OpenBao persistent unseal watcher service, Keycloak VM corrected to runtime-control-lv3, oauth2-proxy internal URL updated, dozzle-agent healthcheck disabled (scratch image).
- fixed ServerClaw OIDC login by moving runtime.env to persistent /etc/lv3/serverclaw/ path, resolved hairpin NAT by adding extra_hosts support to open_webui_runtime, added USER_PERMISSIONS_WORKSPACE_MODELS_ACCESS for model visibility, and made Keycloak startup idempotent by auto-creating the external Docker network
- removed dead Plausible OIDC config (OIDC_DISCOVERY_URI, OIDC_CLIENT_SECRET, extra_hosts, /login redirect) — Plausible CE v3.x dropped community OIDC; auth is now exclusively via oauth2-proxy at the NGINX edge
- removed all PatternFly v5 CSS framework classes from ops portal templates (base, index, entry, task_detail, all partials and macros); portal now uses only custom portal.css classes eliminating the CDN dependency and layout conflicts caused by pf-v5-c-page__sidebar translateX collapse; added repowise to service-capability-catalog and dependency-graph (lifecycle_status planned, ADR 0346)
- adds repowise semantic code search — local corpus builder (repowise_corpus.py) chunks 19k code/doc segments by language, indexer (repowise_index.py) embeds via Ollama nomic-embed-text and stores in Qdrant repowise collection, FastAPI service (repowise_service.py) serves /search with language and document_kind filters; Ansible role repowise_runtime deploys on docker-runtime-lv3; no third-party APIs

## Platform Impact
- no live platform version bump; this release updates repository automation, release metadata, and operator tooling only

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
