# Release 0.177.90

- Date: 2026-03-29

## Summary
- implements ADR 0263 by making the governed ServerClaw memory substrate live on the private platform-context runtime with PostgreSQL canonical memory records, Qdrant semantic recall, local keyword search, CLI memory operations, and exact-main replay evidence on `docker-runtime-lv3`

## Platform Impact
- advances the verified platform baseline to 0.130.60 by promoting the ADR 0263 exact-main live-apply receipt for the private ServerClaw memory substrate on docker-runtime-lv3, verified through the private :8010 health and CLI memory smoke path

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
