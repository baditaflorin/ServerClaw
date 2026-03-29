# Release 0.177.71

- Date: 2026-03-29

## Summary
- replayed ADR 0228 from exact origin/main, kept Windmill as the default browser-first and API-first operations surface on CE v1.662.0, fixed Python 3.11 compatibility for the worker-local generated-portals fallback, and re-verified the green post-merge gate plus representative seeded workflows

## Platform Impact
- Platform version advances to 0.130.49 after the exact-main ADR 0228 replay re-verifies Windmill as the default browser-first and API-first operations surface on CE v1.662.0, including the Python 3.11-safe worker generated-portals fallback and a green post-merge fallback on the live worker checkout.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
