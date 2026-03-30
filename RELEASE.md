# Release 0.177.109

- Date: 2026-03-30

## Summary
- implements ADR 0289 by deploying Directus as the repo-managed REST and GraphQL data API on docker-runtime-lv3, adding the dedicated Postgres plus Keycloak/OIDC bootstrap path, publishing `data.lv3.org` on the shared edge, and recording the canonical mainline Directus live-apply receipt bundle
- implements ADR 0293 by adding the private Temporal durable workflow engine, PostgreSQL-backed history and visibility stores, OpenBao-managed runtime secrets, and the repo-managed `lv3` namespace with exact-main verification on docker-runtime-lv3 and postgres-lv3

## Platform Impact
- adds the repo-managed Directus REST and GraphQL data API, dedicated Postgres and Keycloak bootstrap path, and shared-edge publication at `data.lv3.org`
- adds the private Temporal durable workflow engine with PostgreSQL-backed history and visibility stores, OpenBao-managed runtime secrets, and the repo-managed `lv3` namespace

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
