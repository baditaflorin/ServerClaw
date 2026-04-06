# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- fix: Gitea OAuth2 login — ROOT_URL changed to Tailscale access URL (http://100.64.0.1:3009) to fix OAuth2 state cookie mismatch; remove invalid `groups` scope from OPENID_CONNECT_SCOPES in ctmpl template
- Fixed browser-runner service accessibility — added firewall rules to open port 8096 on docker-runtime-lv3 from management network, all guests, and Docker bridge networks; service now accessible from headscale at http://10.10.10.20:8096/
- ADR 0377/0378: Wire platform knowledge and RAG into Open WebUI — enable Ollama API, Qdrant vector DB backend, nomic-embed-text embeddings, ServerClaw system prompt injection, expose Qdrant port 6333 on host for cross-compose access
- ADR 0376: Credential isolation and agent safety — .gitignore hardening for .local symlink blind spot, pre-commit guard to block .local from index, recovery runbook (recover_local_secrets.sh), agent credential access contract, bootstrap key rotation procedure, server migration security checklist
- wire ADR 0347-0357 agent coordination patterns into all discovery surfaces: AGENTS.md coordination section with code examples, config/integrations/ in .config-locations.yaml, validate_integrations.py + check_provenance_headers.py in scripts discovery, regenerated onboarding packs (service-catalog, automation, fork-bootstrap) now reference all 6 implemented ADRs
- fix Woodpecker OAuth login: add nginx edge + TLS for git.lv3.org, fix WOODPECKER_GITEA_URL to use private IP (cross-host LAN), remove dead gitea_runtime_default external network from Woodpecker compose

- AW-22 + AW-23 + provision-outline-api-token: generic _resolve_service_auth() helper (ADR 0362 gap); Outline agent tools — list-outline-collections, search-outline-documents, get-outline-document, create-outline-document (ADR 0364); provision-outline-api-token agent tool for headless credential rotation via DB

- ADR triage 0347-0358: implement 6 CPU-only ADRs — Integration Contract Registry (config/integrations/, validate_integrations.py), Nginx Fragment Config role (write-validate-reload), File-Domain Locking + Apply Semaphore (platform/locking/file_domain.py extending ADR 0153), Workstream Apply Receipts state machine (platform/workstream_receipts.py), Change Provenance Tagging (Jinja2 macro + check_provenance_headers.py); mark 3 ADRs Superseded (LLM-heavy: 0348, 0352, 0356) and 3 Deferred (0349, 0354, 0358)
- ADR 0375: Certificate validation and concordance enforcement — automated SSL checking for all edge-published domains, pre-push gate integration, Uptime Kuma monitors, and fix playbook for NGINX edge certificate hostname mismatches (ci.lv3.org, bi.lv3.org, grist.lv3.org, paperless.lv3.org, annotate.lv3.org, ntfy.lv3.org); certificate_validator.py now uses certificate-catalog.json (ADR 0101 canonical) as primary source; pre-push gate ADR ref corrected to 0375; validate-certificates Makefile target hooked into configure-edge-publication; back-references added to ADR 0101 and ADR 0273.
- Operational fixes: OpenBao persistent unseal watcher service, Keycloak VM corrected to runtime-control-lv3, oauth2-proxy internal URL updated, dozzle-agent healthcheck disabled (scratch image).
- fixed ServerClaw OIDC login by moving runtime.env to persistent /etc/lv3/serverclaw/ path, resolved hairpin NAT by adding extra_hosts support to open_webui_runtime, added USER_PERMISSIONS_WORKSPACE_MODELS_ACCESS for model visibility, and made Keycloak startup idempotent by auto-creating the external Docker network
- removed dead Plausible OIDC config (OIDC_DISCOVERY_URI, OIDC_CLIENT_SECRET, extra_hosts, /login redirect) — Plausible CE v3.x dropped community OIDC; auth is now exclusively via oauth2-proxy at the NGINX edge
- removed all PatternFly v5 CSS framework classes from ops portal templates (base, index, entry, task_detail, all partials and macros); portal now uses only custom portal.css classes eliminating the CDN dependency and layout conflicts caused by pf-v5-c-page__sidebar translateX collapse; added repowise to service-capability-catalog and dependency-graph (lifecycle_status planned, ADR 0346)
- adds repowise semantic code search — local corpus builder (repowise_corpus.py) chunks 19k code/doc segments by language, indexer (repowise_index.py) embeds via Ollama nomic-embed-text and stores in Qdrant repowise collection, FastAPI service (repowise_service.py) serves /search with language and document_kind filters; Ansible role repowise_runtime deploys on docker-runtime-lv3; no third-party APIs

## Latest Release

- [0.178.30 release notes](docs/release-notes/0.178.30.md)

## Previous Releases

- [0.178.29 release notes](docs/release-notes/0.178.29.md)
- [0.178.28 release notes](docs/release-notes/0.178.28.md)
- [0.178.27 release notes](docs/release-notes/0.178.27.md)
- [0.178.26 release notes](docs/release-notes/0.178.26.md)
- [0.178.25 release notes](docs/release-notes/0.178.25.md)
- [0.178.24 release notes](docs/release-notes/0.178.24.md)
- [0.178.23 release notes](docs/release-notes/0.178.23.md)
- [0.178.22 release notes](docs/release-notes/0.178.22.md)
- [0.178.21 release notes](docs/release-notes/0.178.21.md)
- [0.178.20 release notes](docs/release-notes/0.178.20.md)
- [0.178.19 release notes](docs/release-notes/0.178.19.md)
- [0.178.18 release notes](docs/release-notes/0.178.18.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (369 releases)](docs/release-notes/index/2026.md)
