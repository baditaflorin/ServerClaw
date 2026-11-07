# Release 0.179.60

- Date: 2026-11-07

## Summary
- Warn before either standby courier source reaches its bounded RAM scratch limit, with a critical escalation closer to the limit.
- Alert on missing size telemetry while allowing backup transfers to continue if telemetry cannot be captured.
- Record the guarded deployment, scheduled backup verification and Prometheus rule tests.

## Platform Impact
- Platform 0.179.62 records the verified courier and primary Prometheus alert deployment; no catalog application deployment.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
