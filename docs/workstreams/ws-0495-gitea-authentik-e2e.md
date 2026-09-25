# Gitea Authentik entitlement and end-to-end verification

## Scope

Allow a least-privilege Authentik user to sign in to the private Gitea instance,
while reserving Gitea's `ops/Owners` team mapping for the existing
`platform-admins` group. Add an explicit, separately invoked test-identity
manifest and a browser verification command that does not weaken TLS checks or
print credentials.

## Safety boundaries

- Gitea remains private-only and tailnet-scoped; do not add public edge access.
- The ordinary-user group grants only Gitea authentication. It does not grant
  Authentik administration, Gitea administration, or an organization team.
- The test user is absent from routine identity reconciliation and uses a
  generated password stored only in the ignored local overlay.
- A live reconcile requires an exact deployment-selection preflight and a
  fresh workstream apply receipt. Never bypass TLS verification.

## Verification

- Focused Authentik identity, Gitea runtime, and E2E script tests pass.
- Gitea and Authentik Ansible syntax checks pass.
- Workstream-registry, integration-contract, and Woodpecker's `json`,
  `health-probes`, and `agent-standards` validation lanes pass.
- A temporary Firefox profile trusts only the explicit internal CA; the live
  Gitea login page returned HTTP 200 with normal TLS validation.
- `make validate` currently fails at its generated-vars lane because the base
  checkout lacks `inventory/group_vars/platform_hairpin.yml`; this is a
  pre-existing generated artifact, unrelated to the changes here.
- The full test collection ran but the repository baseline has numerous
  unrelated failures; the changed Gitea/Authenik tests pass separately.

## Live status

The selected Authentik API responds to a read-only identity reconciliation
with no drift. The fresh public checkout's generated platform snapshot does
not match the selected private overlay, so no live identity or Gitea
configuration has been changed. Re-run the governed apply only from a reviewed
deployment worktree whose tracked deployment metadata matches the selected
private overlay.
