# Release 0.177.43

- Date: 2026-03-28

## Summary
- implemented ADR 0225 by installing a durable server-resident ansible-pull reconcile loop on proxmox_florin, bootstrapping a least-privilege Gitea pull identity, and verifying host-local receipts through the private Gitea source

## Platform Impact
- bump platform version after the ADR 0225 merged-main server-resident reconcile replay confirms the private Gitea-backed ansible-pull loop is live from the final integrated commit on proxmox_florin

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
