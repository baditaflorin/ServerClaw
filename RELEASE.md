# Release 0.177.43

- Date: 2026-03-28

## Summary
- implemented ADR 0225 by installing a durable server-resident ansible-pull reconcile loop on proxmox_florin, bootstrapping a least-privilege Gitea pull identity, and verifying host-local receipts through the private Gitea source

## Platform Impact
- bumped the live platform version to 0.130.40 after the rebased ADR 0225 merged-main candidate was published to the private Gitea source as snapshot commit 5b121f700d0f1cd372ef85f24288691fb8a88e0c and `lv3-server-resident-reconciliation.service` completed successfully on proxmox_florin

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
