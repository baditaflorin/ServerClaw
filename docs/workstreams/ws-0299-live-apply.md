# Workstream ws-0299-live-apply: ADR 0299 Live Apply From Latest `origin/main`

- ADR: [ADR 0299](../adr/0299-ntfy-as-the-self-hosted-push-notification-channel-for-programmatic-alert-delivery.md)
- Title: promote ntfy from the private paging gateway into the governed self-hosted push notification channel
- Status: in_progress
- Branch: `codex/ws-0299-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0299-live-apply`
- Owner: codex
- Depends On: `adr-0043`, `adr-0068`, `adr-0077`, `adr-0087`, `adr-0095`, `adr-0172`, `adr-0204`, `adr-0276`, `adr-0280`
- Conflicts With: none

## Scope

- convert ntfy from the private `platform-alerts` paging gateway into the repo-governed public `ntfy.lv3.org` push surface described by ADR 0299
- add the topic registry, image pinning, controller-local secret contracts, OpenBao token seeding, and the service-wrapper automation needed for governed replay
- update Alertmanager, Changedetection, Ansible notifications, Gitea validation failures, and Windmill watchdog or security bridges to use the new ntfy contracts
- live-apply the change from this isolated latest-main worktree, verify the public and private paths end to end, and leave clear receipts plus merge-safe notes behind

## Protected-File Boundaries

- Do not bump `VERSION` on this branch.
- Do not edit numbered release sections in `changelog.md` on this branch.
- Do not update the top-level integrated `README.md` status summary on this branch.
- Do not update `versions/stack.yaml` unless this workstream becomes the final verified integration step on `main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0299-live-apply.md`
- `docs/adr/0299-ntfy-as-the-self-hosted-push-notification-channel-for-programmatic-alert-delivery.md`
- `docs/runbooks/configure-ntfy.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `Makefile`
- `playbooks/ntfy.yml`
- `playbooks/services/ntfy.yml`
- `playbooks/tasks/preflight.yml`
- `playbooks/tasks/notify.yml`
- `collections/ansible_collections/lv3/platform/playbooks/ntfy.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/preflight.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/notify.yml`
- `collections/ansible_collections/lv3/platform/plugins/callback/mutation_audit.py`
- `collections/ansible_collections/lv3/platform/roles/ntfy_runtime/`
- `collections/ansible_collections/lv3/platform/roles/alertmanager_runtime/`
- `collections/ansible_collections/lv3/platform/roles/changedetection_runtime/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/`
- `config/ntfy/server.yml`
- `config/ntfy/topics.yaml`
- `config/subdomain-catalog.json`
- `config/image-catalog.json`
- `config/controller-local-secrets.json`
- `config/secret-catalog.json`
- `config/health-probe-catalog.json`
- `config/service-capability-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/dependency-graph.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/alertmanager/alertmanager.yml`
- `config/windmill/scripts/`
- `scripts/mutation_audit.py`
- `scripts/ntfy_publish.py`
- `.gitea/workflows/validate.yml`
- `receipts/image-scans/`
- `receipts/live-applies/`

## Current Plan

- add the topic and credential registry first so the runtime, secret manifests, and downstream integrations all consume one declared contract
- keep compatibility only where a client forces it, but move governed publishers onto ADR 0299 topic names on this workstream
- validate both `make converge-ntfy` and the generic `make live-apply-service service=ntfy env=production` path before calling the branch complete

## 2026-04-03 Verification Notes

- `make converge-ntfy env=production` completed successfully after catalog and edge publication fixes, including Hetzner DNS convergence, ntfy runtime convergence on `docker-runtime-lv3`, `ntfy.lv3.org` edge publication on `nginx-lv3`, and a controller-side `https://ntfy.lv3.org/v1/health` check.
- direct controller verification of `https://ntfy.lv3.org/platform-ansible-info` no longer times out after adding ntfy-specific edge proxy tuning (`chunked_transfer_encoding`, disabled request buffering, and longer proxy timeouts); the public POST path now returns immediately.
- the remaining runtime mismatch is ntfy authentication reconciliation on `docker-runtime-lv3`: the live `server.yml` still exposes only the older `alertmanager` auth contract, so the public publish path currently returns `401 unauthorized` instead of accepting the governed `ansible` credentials.
- a later branch-local `make converge-ntfy env=production` replay was interrupted after concurrent Docker-runtime activity from other active workstreams left the automation path stuck; the stale run was terminated rather than left contending with shared host changes.
- `make converge-monitoring env=production` advanced through monitoring-stack verification, generated updated host SBOM receipts, and then was intentionally interrupted during later observability replay because it had moved beyond the ntfy-specific verification needed for this workstream pass.

## Remaining For Final Mainline Closeout

- rebase this workstream onto the latest `origin/main` before final integration so the live apply originates from the current mainline truth
- replay ntfy from merged `main`, not the stale branch tip, and verify `python3 scripts/ntfy_publish.py --publisher ansible --topic platform-ansible-info ...` succeeds end to end with repo-managed credentials
- once the merged-main replay succeeds, update ADR 0299 metadata to `Implementation Status: Implemented` and record the first repo version, first platform version, and implementation date
- update the protected integration files on `main` only: `VERSION`, `changelog.md`, `README.md`, and `versions/stack.yaml`

## Merge-To-Main Reminder

- if the branch completes the live apply before the final main integration step, leave the exact remaining protected-file updates spelled out here before ending the session
