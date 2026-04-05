# Release 0.178.6

- Date: 2026-04-05

## Summary
- fully live applies the remaining runtime pool transition by bringing runtime-general and runtime-control online, rebalancing host memory to satisfy ADR 0321, and capturing the verified platform truth from exact mainline

## Platform Impact
- fully live applies the remaining runtime pool transition from exact main, bringing runtime-general and runtime-control online, retiring legacy control-plane copies from docker-runtime-lv3, and recording the verified post-apply platform truth

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
