# Release 0.177.116

- Date: 2026-03-31

## Summary
- implements ADR 0290 by bringing the private Redpanda Kafka-compatible streaming platform, topic reconciliation, and authenticated Admin API, HTTP Proxy, and Schema Registry runtime onto main after the exact-main governed replay on docker-runtime-lv3

## Platform Impact
- Platform version remains 0.130.75 while release 0.177.116 records the already-verified ADR 0290 Redpanda runtime and canonical mainline receipt on top of the current origin/main baseline.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
