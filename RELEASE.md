# Release 0.177.88

- Date: 2026-03-29

## Summary
- implemented ADR 0266 by adding declared validation-runner contracts, per-run environment attestation, runner-aware gate scheduling, and recorded build handoff evidence across the remote build server, controller fallback, and worker post-merge paths

## Platform Impact
- platform version advances to 0.130.60 after ADR 0266 re-verifies declared validation-runner contracts, build-server environment attestation, worker-local post-merge runner identity, and the exact-main Windmill replay on the current 0.130.59 baseline, including the OpenBao restart hardening needed to keep that replay deterministic

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
