# Gitea Authentik OIDC access and E2E verification

## Outcome

Allow Authentik users in the narrowly scoped `gitea-users` group to sign in to
Gitea, while keeping the existing platform-admin-to-`ops/Owners` mapping intact.
Add a separately provisioned, non-admin `gitea-e2e` identity and a fresh-browser
test that proves the complete Authentik-to-Gitea login path.

## Safety boundaries

- The test identity is absent from the normal identity manifest; provisioning
  requires explicitly selecting `config/authentik/test-identities.yaml`.
- Its initial password is generated only under the ignored local overlay with
  mode `0600`; scripts and CI must not print it.
- The browser test validates HTTPS and the local root CA, and confirms the
  authenticated Gitea user is `gitea-e2e` with `is_admin: false`.
- Gitea's `ops/Owners` team mapping remains restricted to platform admins.
- Service-completeness validation checks the affected service for scoped
  changes; global catalog or unscoped changes still run the full inventory.
- The full data-model gate remains enabled; topology identity placeholders are
  resolved with one identity-file load per validation rather than one per YAML
  scalar.

## Verification

- Unit tests cover the identity group, group membership, non-admin test
  manifest, secret-file handling, TLS enforcement, and authenticated-user
  assertions.
- Before applying, deployment selection is validated with explicit identity
  and topology files plus Gitea's required database and runner hosts.
- Live verification reconciles the stable Authentik manifest, explicitly
  applies the test identity, converges Gitea, then completes a browser login
  and checks the Gitea current-user API from that browser session.

## Status

Merged in PR #239 and applied to the selected production deployment on
2026-09-25. The fresh Firefox E2E completed Authentik authentication, returned
to the Gitea dashboard as `gitea-e2e`, and verified the account is not an
administrator with TLS validation enabled and the internal CA trusted only in
the temporary test profile. The live apply receipt records the converge,
backup, browser, and security-scan evidence; the test password remains only in
the ignored local overlay and was delivered separately to the operator by
email.
