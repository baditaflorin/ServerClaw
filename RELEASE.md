# Release 0.177.44

- Date: 2026-03-28

## Summary
- integrates ADR 0231 into main by replacing the control-plane backup service's plaintext OpenBao token and baked-in Windmill DSN with host-native OpenBao Agent delivery through systemd credentials

## Platform Impact
- no live platform version bump; this release records the merged ADR 0231 host-native OpenBao Agent plus systemd-credentials replay already verified on platform 0.130.38 while the current main baseline remains 0.130.40

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
