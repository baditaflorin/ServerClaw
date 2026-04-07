# Changelog

This file is now the release scratchpad and index.

Detailed platform change history lives in the generated deployment history portal:

- local build: [build/changelog-portal/index.html](build/changelog-portal/index.html)
- published deployment portal: configure this in your fork if you publish generated docs
- generation command: `make generate-changelog-portal`

Versioned release notes live under [docs/release-notes/README.md](docs/release-notes/README.md).

## Unreleased

- Neko multi-instance browser sessions: each user gets an isolated Neko container keyed by Keycloak email; adding/removing entries in neko_instances auto-provisions/deprovisions the container and Keycloak user; NGINX routes authenticated users to their container via email map; single-instance containers removed in favour of the loop-based neko_runtime role

- fix ops.lv3.org auth loop — expire both session and PKCE CSRF cookies on oauth2-proxy 500 at /oauth2/callback, then redirect to Keycloak logout to kill the server-side session; without this, stale code_verifier in the CSRF cookie caused "Code not valid" on every login attempt

- add LiteLLM Proxy + LibreChat to replace One API + Open WebUI — portable DTOs in config/llm-gateway/ decouple model catalog, consumer keys, auth, and RAG from specific tools; LiteLLM on port 4000 with YAML-driven model routing and fallback chains; LibreChat with native system prompt presets (no Ollama model creation hack); both roles follow service scaffold pattern with OpenBao sidecar

- deploy Neko remote desktop at browser.lv3.org (ADR 0380) — dedicated runtime-comms-lv3 VM (VMID 121, 10.10.10.21), Chromium over WebRTC with host-mode networking for UDP media (50000-60000), TLS cert via certbot, published through nginx_edge_publication role with 3600s proxy timeout for long-lived streaming sessions

- ADR governance system: pre-commit hook validates ADR status transitions (requires evidence for upgrades, reason for downgrades), Plane integration syncs 406 ADRs for team visibility, quarterly audit detects implementation drift automatically

- fix redirect loop: stale session reset now redirects to Keycloak logout (kills Keycloak session + clears sso.lv3.org cookie) instead of /oauth2/sign_in, preventing Keycloak from auto-logging back in with a poisoned session

- NGINX auto-clears stale session cookie on oauth2-proxy 500 at /oauth2/callback — users no longer see 500 errors or need to manually clear cookies after Keycloak restarts

- made Keycloak Outline user reconciliation optional (keycloak_reconcile_outline_users) to unblock testing when Keycloak API becomes unresponsive; Gitea deployment no longer blocked by Outline reconciliation timeout
- fixed Gitea and Keycloak convergence by correcting argument_specs contract (conventional variables from defaults must not be marked required inputs); all ADR 0373 pattern variables now properly defined in role defaults
- deploy serverclaw:latest with baked-in system prompt as the default named model in chat.lv3.org; fix derive_service_defaults guard (use open_webui_site_dir is not defined), fix Ollama api/create URL for remote Ollama instance, add keycloak_local_artifact_dir fallback default, migrate woodpecker_runtime defaults to ADR 0373 pattern

- Operational fixes: OpenBao persistent unseal watcher service, Keycloak VM corrected to runtime-control-lv3, oauth2-proxy internal URL updated, dozzle-agent healthcheck disabled (scratch image).
- fixed ServerClaw OIDC login by moving runtime.env to persistent /etc/lv3/serverclaw/ path, resolved hairpin NAT by adding extra_hosts support to open_webui_runtime, added USER_PERMISSIONS_WORKSPACE_MODELS_ACCESS for model visibility, and made Keycloak startup idempotent by auto-creating the external Docker network
- removed dead Plausible OIDC config (OIDC_DISCOVERY_URI, OIDC_CLIENT_SECRET, extra_hosts, /login redirect) — Plausible CE v3.x dropped community OIDC; auth is now exclusively via oauth2-proxy at the NGINX edge
- removed all PatternFly v5 CSS framework classes from ops portal templates (base, index, entry, task_detail, all partials and macros); portal now uses only custom portal.css classes eliminating the CDN dependency and layout conflicts caused by pf-v5-c-page__sidebar translateX collapse; added repowise to service-capability-catalog and dependency-graph (lifecycle_status planned, ADR 0346)
- adds repowise semantic code search — local corpus builder (repowise_corpus.py) chunks 19k code/doc segments by language, indexer (repowise_index.py) embeds via Ollama nomic-embed-text and stores in Qdrant repowise collection, FastAPI service (repowise_service.py) serves /search with language and document_kind filters; Ansible role repowise_runtime deploys on docker-runtime-lv3; no third-party APIs

## Latest Release

- [0.178.55 release notes](docs/release-notes/0.178.55.md)

## Previous Releases

- [0.178.54 release notes](docs/release-notes/0.178.54.md)
- [0.178.53 release notes](docs/release-notes/0.178.53.md)
- [0.178.52 release notes](docs/release-notes/0.178.52.md)
- [0.178.51 release notes](docs/release-notes/0.178.51.md)
- [0.178.50 release notes](docs/release-notes/0.178.50.md)
- [0.178.49 release notes](docs/release-notes/0.178.49.md)
- [0.178.48 release notes](docs/release-notes/0.178.48.md)
- [0.178.47 release notes](docs/release-notes/0.178.47.md)
- [0.178.46 release notes](docs/release-notes/0.178.46.md)
- [0.178.45 release notes](docs/release-notes/0.178.45.md)
- [0.178.44 release notes](docs/release-notes/0.178.44.md)
- [0.178.43 release notes](docs/release-notes/0.178.43.md)

## Release Archives

- [Release note archives](docs/release-notes/index/README.md)
- [2026 (391 releases)](docs/release-notes/index/2026.md)
