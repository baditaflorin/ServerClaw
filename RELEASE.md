# Release 0.177.96

- Date: 2026-03-30

## Summary
- integrates ADR 0282 into main by replaying Mailpit as the private development SMTP interceptor and the non-production SMTP contract onto the merged 0.177.95 / 0.130.63 baseline, preserving the exact-main Mailpit verification from docker-runtime-lv3 and monitoring-lv3 without advancing platform_version again

## Platform Impact
- ADR 0282 is already live on platform version 0.130.60; this exact-main integration replays Mailpit onto the merged 0.177.95 / 0.130.63 baseline without advancing platform_version again.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
