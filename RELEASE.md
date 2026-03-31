# Release 0.177.124

- Date: 2026-03-31

## Summary
- implements ADR 0277 by bringing the private Typesense structured-search
  runtime, controller proxy, API gateway search route, and recorded exact-main
  live-apply evidence onto `main`

## Platform Impact
- advances the tracked platform version to `0.130.79` after the exact-main
  Typesense replay re-verified the private controller endpoint, the
  `platform-services` collection, the authenticated
  `/v1/platform/search/structured` path, and runtime assurance from the latest
  realistic `origin/main` baseline

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
