# Release 0.157.2

- Date: 2026-03-25

## Summary
- Fix the delegated Windmill config-merge migration so the live `main` converge executes `psql` as the PostgreSQL service user instead of `root`.
- Keep the current ADR 0165 and Windmill rollout path unblocked by aligning the delegated migration step with the existing `windmill_postgres` task model.

## Platform Impact
- repository version advances to `0.157.2`; platform version remains `0.130.4` until the current `main` live apply is completed and verified

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
