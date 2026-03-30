# Release 0.177.109

- Date: 2026-03-30

## Summary
- implements ADR 0288 by adding the repo-managed Flagsmith runtime, OpenBao-backed seed and environment key publication, public `flags.lv3.org` edge routing, and live verification hardening for sparse feature-state API responses plus Docker bridge-chain recovery
- implements ADR 0289 by deploying Directus as the repo-managed REST and GraphQL data API on docker-runtime-lv3, adding the dedicated Postgres plus Keycloak/OIDC bootstrap path, publishing `data.lv3.org` on the shared edge, and recording the canonical mainline Directus live-apply receipt bundle
- implements ADR 0293 by adding the private Temporal durable workflow engine, PostgreSQL-backed history and visibility stores, OpenBao-managed runtime secrets, and the repo-managed `lv3` namespace with exact-main verification on docker-runtime-lv3 and postgres-lv3

## Platform Impact
- preserves the verified `0.177.109` / `0.130.72` mainline baseline while integrating the public Flagsmith service behind the shared oauth2-proxy boundary on `flags.lv3.org`
- adds the repo-managed Directus REST and GraphQL data API, dedicated Postgres plus Keycloak bootstrap path, and shared-edge publication at `data.lv3.org`
- adds the private Temporal durable workflow engine with PostgreSQL-backed history and visibility stores, OpenBao-managed runtime secrets, and the repo-managed `lv3` namespace

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
