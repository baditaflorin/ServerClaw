# Identity Taxonomy And Managed Principals

## Purpose

This runbook turns [ADR 0046](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0046-identity-classes-for-humans-services-and-agents.md) into an enforced repository contract.

It defines:

- the four allowed identity classes
- the current named principals already in use on the platform
- the metadata every future identity must carry in [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)

## Canonical Sources

- [versions/stack.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/versions/stack.yaml)
  - `desired_state.identity_taxonomy`: required class definitions and managed identities
  - `observed_state.identity_taxonomy`: the current review date and the principals confirmed to exist
- [scripts/validate_repository_data_models.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_repository_data_models.py)
  - enforces the taxonomy structure in the standard `make validate` gate
- [docs/runbooks/proxmox-api-automation.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/proxmox-api-automation.md)
  - operational lifecycle for the current Proxmox agent identity
- [config/controller-local-secrets.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/controller-local-secrets.json)
  - controller-local secret inventory for credential material stored outside git

## Allowed Classes

### Human operator

- one named person owns the identity
- interactive administration and review only
- never reused as a service or workflow identity

### Service

- one application or stack owns the identity
- no human login
- scoped to that runtime surface only

### Agent

- owned by repo automation, a workflow runner, or another approved automation surface
- narrower than break-glass
- never borrowed from a human identity

### Break-glass

- emergency recovery only
- not used for steady-state automation
- rotated after any real use

## Required Metadata

Every managed identity entry in `versions/stack.yaml` must define:

- `owner`
- `purpose`
- `scope_boundary`
- `rotation_or_expiry`
- `credential_storage`

The standard data-model validator fails if any of these fields are missing.

## Current Managed Principals

| Principal | Class | Owner | Main Surface | Notes |
| --- | --- | --- | --- | --- |
| `ops` | `human_operator` | `Florin Badita` | Proxmox host and guest Linux administration | Currently shares the bootstrap SSH key material with the break-glass `root` path; ADR 0047 should retire that overlap. |
| `ops@pam` | `human_operator` | `Florin Badita` | Routine Proxmox UI and CLI administration | Protected with TOTP and scoped to Proxmox administration. |
| `lv3-automation@pve` | `agent` | `Repository automation` | Proxmox API automation | Uses a privilege-separated token stored only under `.local/proxmox-api`. |
| `server@lv3.org` | `service` | `Mail platform runtime` | Managed mailbox and authenticated mail submission | Backed by the internal mail platform on `docker-runtime-lv3`. |
| `alerts@lv3.org` | `service` | `Platform operations` | Operator alert sender profile | Scoped to outbound alert delivery through the managed mail gateway and backed by profile-specific credentials under `.local/mail-platform/profiles/`. |
| `platform@lv3.org` | `service` | `Platform services` | Platform transactional sender profile | Scoped to repo-managed service notifications through the managed mail gateway. |
| `agents@lv3.org` | `agent` | `Repository automation` | Agent and workflow report sender profile | Scoped to automated report delivery through the managed mail gateway and rejected if reused for another profile. |
| `root` | `break_glass` | `Florin Badita` | Emergency Proxmox host recovery | Key-only and reserved for recovery. Rotate immediately after any real use. |

## Change Rules

When introducing a new identity:

1. Choose one of the four classes before provisioning it anywhere.
2. Add the identity to `desired_state.identity_taxonomy.managed_identities`.
3. Record where the credential material lives in `credential_storage`.
4. Update the relevant runbook that provisions or rotates that identity.
5. If the identity is already live, update `observed_state.identity_taxonomy` in the same integration change.
6. Run `make validate`.

Do not introduce:

- shared human credentials
- agent tooling that logs in as a human
- break-glass identities reused for recurring automation
- undocumented local secret files or API tokens

## Review Checklist

Use this before merging any identity-related change:

- the principal is listed in `versions/stack.yaml`
- the class matches the intended use
- the scope boundary is narrower than break-glass
- the credential storage location is documented
- the relevant runbook explains provisioning or rotation
- `make validate` passes
