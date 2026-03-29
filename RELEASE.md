# Release 0.177.86

- Date: 2026-03-29

## Summary
- implemented ADR 0266 by adding declared validation-runner contracts, per-run environment attestation, runner-aware gate scheduling, and recorded build handoff evidence across the remote build server, controller fallback, and worker post-merge paths

## Platform Impact
- platform version advances to 0.130.59 after the exact-main ADR 0266 replay re-verifies declared runner contracts, build-server and local-fallback gate scheduling, and worker post-merge validation on top of the 0.130.58 matrix-synapse baseline

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
