# Release 0.112.0

- Date: 2026-03-24

## Summary
- Added ADR 0116 deterministic workflow risk scoring, compiled intent output, and `AUTO` / `SOFT` / `HARD` / `BLOCK` gating to `lv3 run`.
- Added repo-managed risk scoring weights, fallback overrides, and a Windmill-compatible calibration script for tuning false positive and false negative rates.

## Platform Impact
- Added deterministic workflow risk scoring and lv3 run approval gates.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
