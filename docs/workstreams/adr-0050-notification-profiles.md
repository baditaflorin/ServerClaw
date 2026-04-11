# Workstream ADR 0050: Transactional Email And Notification Profiles

- ADR: [ADR 0050](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0050-transactional-email-and-notification-profiles.md)
- Title: Mail sender profiles for platform, operators, and agents
- Status: live_applied
- Branch: `codex/adr-0050-notification-profiles`
- Worktree: `../proxmox-host_server-notification-profiles`
- Owner: codex
- Depends On: `adr-0041-email-platform`, `adr-0046-identity-classes`
- Conflicts With: none
- Shared Surfaces: Stalwart, SMTP submission, notifications, agent reports

## Scope

- define sender profiles on top of the chosen mail platform
- separate operator, platform, and agent mail identities
- make email send a governed capability instead of a generic SMTP login

## Non-Goals

- replacing ADR 0041

## Expected Repo Surfaces

- `docs/adr/0050-transactional-email-and-notification-profiles.md`
- `docs/workstreams/adr-0050-notification-profiles.md`
- `docs/runbooks/configure-mail-platform.md`
- `playbooks/mail-platform-notification-profiles-verify.yml`
- `config/controller-local-secrets.json`
- `workstreams.yaml`

## Expected Live Surfaces

- dedicated sender profiles for alerts, reports, and transactional mail
- clearer audit and revocation paths for outbound mail

## Verification

- `make syntax-check-mail-platform`
- `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/mail-platform-notification-profiles-verify.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --limit docker-runtime`

## Merge Criteria

- dedicated sender profiles exist for operator alerts, platform transactional mail, and agent reports
- each profile is backed by a scoped mail-gateway credential and a dedicated sender identity
- live verification proves profile-scoped send behavior and per-profile delivery counters

## Live Apply Notes

- Live apply completed on `2026-03-22` from the `main` integration worktree using the repo-managed mail platform automation with a guest-only `--limit` because DNS and host ingress were already converged.
- Scoped verification proved that the operator-alerts API key is rejected when it attempts to send as `platform-transactional`.
- Focused live delivery verification succeeded for `alerts@example.com`, `platform@example.com`, and `agents@example.com`, and the mail gateway state recorded one successful Brevo send for each profile.
