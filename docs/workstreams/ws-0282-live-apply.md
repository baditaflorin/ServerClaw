# Workstream ws-0282-live-apply: Live Apply ADR 0282 From Latest `origin/main`

- ADR: [ADR 0282](../adr/0282-mailpit-as-the-smtp-development-mail-interceptor.md)
- Title: Deploy Mailpit as the private SMTP development and staging mail interceptor
- Status: live_applied
- Included In Repo Version: 0.177.94
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0282-mailpit-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.60
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0282-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0282-live-apply`
- Owner: codex
- Depends On: `adr-0041`, `adr-0107`, `adr-0165`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0282`, `docs/workstreams/ws-0282-live-apply.md`, `docs/runbooks/configure-mailpit.md`, `docs/runbooks/configure-mail-platform.md`, `inventory/group_vars/all.yml`, `inventory/group_vars/staging.yml`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/mailpit.yml`, `playbooks/services/mailpit.yml`, `collections/ansible_collections/lv3/platform/roles/mailpit_runtime/`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`, `playbooks/mail-platform-verify.yml`, `collections/ansible_collections/lv3/platform/playbooks/mail-platform-verify.yml`, `config/*catalog*.json`, `Makefile`, `scripts/generate_platform_vars.py`, `scripts/validate_repo.sh`, `receipts/image-scans/`, `receipts/live-applies/`

## Purpose

Implement ADR 0282 by making Mailpit the repo-managed private SMTP
interceptor on `docker-runtime-lv3`, wiring the non-production SMTP contract to
that service, and preserving enough branch-local state that a later exact-main
replay can promote the service onto the protected `main` surfaces safely.

## Branch-Local Delivery

- `ba64cd226` added the repo-managed Mailpit runtime, the staging SMTP
  override contract, the Mailpit verification playbook path, and the supporting
  catalog, workflow, and image-scan surfaces.
- `52517d2c2` fixed the Mailpit mail-platform verification syntax-check path so
  the staging probe contract could be validated through repo automation.
- `fb1ebb6b9` repaired the topology lookup so the first governed replay could
  traverse the canonical host variables cleanly after rebases.
- `c70973105` refreshed the rebased branch-local proof and preserved the
  branch-local live-apply receipt after the earlier origin/main history
  changed underneath the workstream.

## Verification

- The first synchronized mainline proof on 2026-03-30 is preserved in
  `receipts/live-applies/2026-03-30-adr-0282-mailpit-live-apply.json`, and it
  records the first live platform version where Mailpit became true:
  `0.130.60`.
- The authoritative exact-main replay now uses repository version `0.177.93`
  from committed source `9f241acdf0ec64f97b42c5494c5b8d2e2f36e6e1` after
  refreshing this work onto `origin/main` commit
  `46df65e7f2227ca79a38035d2d24f53b6c02b5f8`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=mailpit env=production`
  completed successfully on that synchronized tree with final recap
  `docker-runtime-lv3 : ok=115 changed=4 unreachable=0 failed=0 skipped=18 rescued=0 ignored=0`.
- Fresh guest-local verification returned Mailpit info with
  `Version=v1.29.5`, `Messages=1`, and `SMTPAccepted=7`.
- A fresh probe from `monitoring-lv3` deleted previous Mailpit messages, sent
  SMTP to `10.10.10.20:1025`, and confirmed exactly one matching captured
  message through `http://10.10.10.20:8025/api/v1/messages`.

## Outcome

- ADR 0282 is now implemented on integrated repo version `0.177.94`.
- Mailpit first became true on platform version `0.130.60`, while the current
  integrated mainline baseline remains `0.130.62` with no additional
  platform-version bump.
- `receipts/live-applies/2026-03-30-adr-0282-mailpit-mainline-live-apply.json`
  supersedes the branch-local receipt as the canonical proof for `mailpit`
  while preserving the earlier branch-local receipt in the audit trail.
