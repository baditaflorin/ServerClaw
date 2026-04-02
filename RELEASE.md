# Release 0.177.147

- Date: 2026-04-02

## Summary
- records ADR 0312 exact-main verification on the current mainline by preserving the already-live shared notification center and activity timeline from repository version 0.177.146 and platform version 0.130.92 while hardening validation-gate status handling and remote execution against empty state files and concurrent snapshot-run collisions

## Platform Impact
- no live platform version bump; this release preserves the already-live ADR 0312 portal baseline while hardening validation-gate automation and remote execution against empty state files and concurrent run collisions

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
