# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- made Keycloak Outline user reconciliation optional (keycloak_reconcile_outline_users) to unblock testing when Keycloak API becomes unresponsive; Gitea deployment no longer blocked by Outline reconciliation timeout
- fixed Gitea and Keycloak convergence by correcting argument_specs contract (conventional variables from defaults must not be marked required inputs); all ADR 0373 pattern variables now properly defined in role defaults
- deploy serverclaw:latest with baked-in system prompt as the default named model in chat.lv3.org; fix derive_service_defaults guard (use open_webui_site_dir is not defined), fix Ollama api/create URL for remote Ollama instance, add keycloak_local_artifact_dir fallback default, migrate woodpecker_runtime defaults to ADR 0373 pattern

- Operational fixes: OpenBao persistent unseal watcher service, Keycloak VM corrected to runtime-control-lv3, oauth2-proxy internal URL updated, dozzle-agent healthcheck disabled (scratch image).
- fixed ServerClaw OIDC login by moving runtime.env to persistent /etc/lv3/serverclaw/ path, resolved hairpin NAT by adding extra_hosts support to open_webui_runtime, added USER_PERMISSIONS_WORKSPACE_MODELS_ACCESS for model visibility, and made Keycloak startup idempotent by auto-creating the external Docker network
- removed dead Plausible OIDC config (OIDC_DISCOVERY_URI, OIDC_CLIENT_SECRET, extra_hosts, /login redirect) — Plausible CE v3.x dropped community OIDC; auth is now exclusively via oauth2-proxy at the NGINX edge
- removed all PatternFly v5 CSS framework classes from ops portal templates (base, index, entry, task_detail, all partials and macros); portal now uses only custom portal.css classes eliminating the CDN dependency and layout conflicts caused by pf-v5-c-page__sidebar translateX collapse; added repowise to service-capability-catalog and dependency-graph (lifecycle_status planned, ADR 0346)
- adds repowise semantic code search — local corpus builder (repowise_corpus.py) chunks 19k code/doc segments by language, indexer (repowise_index.py) embeds via Ollama nomic-embed-text and stores in Qdrant repowise collection, FastAPI service (repowise_service.py) serves /search with language and document_kind filters; Ansible role repowise_runtime deploys on docker-runtime-lv3; no third-party APIs

## Latest Release

- [0.178.44 release notes](docs/release-notes/0.178.44.md)

## Previous Releases

- [0.178.43 release notes](docs/release-notes/0.178.43.md)
- [0.178.42 release notes](docs/release-notes/0.178.42.md)
- [0.178.39 release notes](docs/release-notes/0.178.39.md)
- [0.178.38 release notes](docs/release-notes/0.178.38.md)
- [0.178.36 release notes](docs/release-notes/0.178.36.md)
- [0.178.35 release notes](docs/release-notes/0.178.35.md)
- [0.178.34 release notes](docs/release-notes/0.178.34.md)
- [0.178.33 release notes](docs/release-notes/0.178.33.md)
- [0.178.32 release notes](docs/release-notes/0.178.32.md)
- [0.178.31 release notes](docs/release-notes/0.178.31.md)
- [0.178.30 release notes](docs/release-notes/0.178.30.md)
- [0.178.29 release notes](docs/release-notes/0.178.29.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (380 releases)](docs/release-notes/index/2026.md)
