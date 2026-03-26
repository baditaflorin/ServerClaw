# Release 0.169.0

- Date: 2026-03-26

## Summary
- publish the repo-generated Homepage dashboard at `https://home.lv3.org` through the shared authenticated edge, with generated service and bookmark catalogs served from `docker-runtime-lv3`
- fix the Homepage converge workflow so `make converge-homepage` uses the working Proxmox jump path and skips unrelated generated static-dir sync during edge publication

## Platform Impact
- repository version advances to `0.169.0`; platform version advances to `0.130.19` with the ADR 0152 Homepage live-apply receipt recorded from `main`.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
