# WS-0532: Direct read-only PostgreSQL access for DBeaver

## Status

In progress. The VM701 PostgreSQL host rules now require TLS and accept the
read-only DBeaver login only for the production database. The Tailscale grant is
pending the policy pull request and live apply. The direct TCP check remains
blocked until that grant is applied.

## Goal

Connect DBeaver Community directly to the production PostgreSQL primary over the
private tailnet, using the existing database-scoped read-only login.

## Change

- Add one tested tailnet grant from the operator device to the PostgreSQL VM on
  TCP 5432.
- Require TLS in PostgreSQL and bind the source address to the approved login
  and production database. Reject other database and role combinations from
  that source.
- Keep DBeaver's connection marked read-only.

## Verification and rollback

- Validate the policy offline, run its focused unit tests, and plan against the
  live tailnet. CI must pass on the exact pull-request head before merge.
- Apply the merged additive policy through the CT108 policy sync path, then
  verify a direct TLS connection and read-only database access.
- Confirm the production database is unavailable to this login over non-TLS or
  for any other database. Revert the grant and restore the saved PostgreSQL
  HBA backup to remove this route.
