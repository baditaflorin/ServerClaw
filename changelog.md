# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- fix Woodpecker OAuth login: add nginx edge + TLS for git.lv3.org, fix WOODPECKER_GITEA_URL to use private IP (cross-host LAN), remove dead gitea_runtime_default external network from Woodpecker compose

- AW-22 + AW-23 + provision-outline-api-token: generic _resolve_service_auth() helper (ADR 0362 gap); Outline agent tools — list-outline-collections, search-outline-documents, get-outline-document, create-outline-document (ADR 0364); provision-outline-api-token agent tool for headless credential rotation via DB

- ADR triage 0347-0358: implement 6 CPU-only ADRs — Integration Contract Registry (config/integrations/, validate_integrations.py), Nginx Fragment Config role (write-validate-reload), File-Domain Locking + Apply Semaphore (platform/locking/file_domain.py extending ADR 0153), Workstream Apply Receipts state machine (platform/workstream_receipts.py), Change Provenance Tagging (Jinja2 macro + check_provenance_headers.py); mark 3 ADRs Superseded (LLM-heavy: 0348, 0352, 0356) and 3 Deferred (0349, 0354, 0358)
- ADR 0375: Certificate validation and concordance enforcement — automated SSL checking for all edge-published domains, pre-push gate integration, Uptime Kuma monitors, and fix playbook for NGINX edge certificate hostname mismatches (ci.lv3.org, bi.lv3.org, grist.lv3.org, paperless.lv3.org, annotate.lv3.org, ntfy.lv3.org).
- Operational fixes: OpenBao persistent unseal watcher service, Keycloak VM corrected to runtime-control-lv3, oauth2-proxy internal URL updated, dozzle-agent healthcheck disabled (scratch image).
- fixed ServerClaw OIDC login by moving runtime.env to persistent /etc/lv3/serverclaw/ path, resolved hairpin NAT by adding extra_hosts support to open_webui_runtime, added USER_PERMISSIONS_WORKSPACE_MODELS_ACCESS for model visibility, and made Keycloak startup idempotent by auto-creating the external Docker network
- removed dead Plausible OIDC config (OIDC_DISCOVERY_URI, OIDC_CLIENT_SECRET, extra_hosts, /login redirect) — Plausible CE v3.x dropped community OIDC; auth is now exclusively via oauth2-proxy at the NGINX edge
- removed all PatternFly v5 CSS framework classes from ops portal templates (base, index, entry, task_detail, all partials and macros); portal now uses only custom portal.css classes eliminating the CDN dependency and layout conflicts caused by pf-v5-c-page__sidebar translateX collapse; added repowise to service-capability-catalog and dependency-graph (lifecycle_status planned, ADR 0346)
- adds repowise semantic code search — local corpus builder (repowise_corpus.py) chunks 19k code/doc segments by language, indexer (repowise_index.py) embeds via Ollama nomic-embed-text and stores in Qdrant repowise collection, FastAPI service (repowise_service.py) serves /search with language and document_kind filters; Ansible role repowise_runtime deploys on docker-runtime-lv3; no third-party APIs

## Latest Release

- [0.178.24 release notes](docs/release-notes/0.178.24.md)

## Previous Releases

- [0.178.23 release notes](docs/release-notes/0.178.23.md)
- [0.178.22 release notes](docs/release-notes/0.178.22.md)
- [0.178.21 release notes](docs/release-notes/0.178.21.md)
- [0.178.20 release notes](docs/release-notes/0.178.20.md)
- [0.178.19 release notes](docs/release-notes/0.178.19.md)
- [0.178.18 release notes](docs/release-notes/0.178.18.md)
- [0.178.17 release notes](docs/release-notes/0.178.17.md)
- [0.178.16 release notes](docs/release-notes/0.178.16.md)
- [0.178.15 release notes](docs/release-notes/0.178.15.md)
- [0.178.14 release notes](docs/release-notes/0.178.14.md)
- [0.178.13 release notes](docs/release-notes/0.178.13.md)
- [0.178.12 release notes](docs/release-notes/0.178.12.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (363 releases)](docs/release-notes/index/2026.md)
