# Release 0.119.1

- Date: 2026-03-24

## Summary
- Fixed the `ops.lv3.org` login redirect so oauth2-proxy no longer requests an invalid literal `groups` scope from Keycloak.
- Added a regression test for the public-edge OIDC auth role and documented the `invalid_scope` recovery path in the ops portal runbook.
- Re-converged the live public edge so the running auth proxy now redirects with `scope=openid profile email`.

## Platform Impact
- repository version advances to `0.119.1`; live platform version advances to `0.114.3` after the auth-proxy scope fix was applied on `nginx-lv3`

## Upgrade Guide
- [docs/upgrade/v1.md](docs/upgrade/v1.md)
