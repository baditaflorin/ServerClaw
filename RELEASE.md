# Release 0.177.20

- Date: 2026-03-28

## Summary
- implemented ADR 0188 failover rehearsal gating so redundancy reporting now distinguishes declared tiers from currently proven tiers and the unproven PostgreSQL warm-standby path is surfaced as implemented `R0`

## Platform Impact
- no live platform version bump; this release publishes ADR 0188 rehearsal-gated redundancy reporting and records the verified PostgreSQL warm-standby gap as implemented R0 until a fresh passing failover rehearsal exists

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
