# Release 0.177.130

- Date: 2026-04-01

## Summary
- accepts ADRs 0319 through 0323 to split the overloaded shared runtime into pool-scoped deployment lanes, raise the governed runtime memory envelope, and add bounded memory-pressure autoscaling rules for elastic services before more workloads are added to the platform

## Platform Impact
- no live platform version bump; this release records a repo-only runtime-pool partitioning, memory-envelope, and bounded autoscaling architecture bundle for future implementation

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
