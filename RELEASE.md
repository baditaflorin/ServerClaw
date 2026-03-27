# Release 0.177.15

- Date: 2026-03-28

## Summary
- completed ADR 0192 by separating `ha_reserved`, `recovery_reserved`, and `preview_burst` capacity classes in mainline automation and recording the verified live apply evidence for preview and restore admission checks

## Platform Impact
- platform_version remains 0.130.31; ADR 0192 capacity-class admission and reporting are now integrated on main, and canonical stack state records the 2026-03-27 live-apply receipt

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
