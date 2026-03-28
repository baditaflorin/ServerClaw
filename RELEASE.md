# Release 0.177.30

- Date: 2026-03-28

## Summary
- integrated ADR 0194 into the latest `origin/main` by carrying the verified Coolify repo-deploy lane forward on top of the newer mainline, preserving the protected dashboard publication, wildcard app ingress, and governed `lv3 deploy-repo` path as canonical repo truth

## Platform Impact
- no platform version bump; Coolify remains live on platform version `0.130.35`, and this mainline release records the verified repo-managed rollout on top of the newer Dify-inclusive mainline.

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
