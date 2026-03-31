# Release 0.177.119

- Date: 2026-03-31

## Summary
- integrates ADR 0306 into main by adding repo-managed Checkov IaC policy scanning to the shared validation gate, build-server remote validation, and the self-hosted validate workflow while preserving the already-current platform baseline 0.130.77 and the earlier exact-main hosted verification proof first established on 0.130.75

## Platform Impact
- Platform version remains 0.130.77 while ADR 0306 is integrated on main with repo-managed Checkov IaC policy scanning and the earlier exact-main hosted verification proof first established on 0.130.75.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
