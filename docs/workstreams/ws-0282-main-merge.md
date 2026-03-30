# Workstream ws-0282-main-merge

- ADR: [ADR 0282](../adr/0282-mailpit-as-the-smtp-development-mail-interceptor.md)
- Title: Integrate ADR 0282 Mailpit exact-main replay onto `origin/main`
- Status: merged
- Included In Repo Version: 0.177.95
- Platform Version Observed During Integration: 0.130.62
- Release Date: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0282-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0282-main-merge`
- Owner: codex
- Depends On: `ws-0282-live-apply`

## Purpose

Carry the verified ADR 0282 Mailpit live-apply branch onto the newest
available `origin/main`, rerun the exact-main Mailpit replay from committed
source on that synchronized baseline, cut the protected release and
canonical-truth surfaces from the resulting tree, and publish the Mailpit
rollout on `main` without inventing a new platform-version bump after Mailpit
was already live on `0.130.60`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0282-main-merge.md`
- `docs/workstreams/ws-0282-live-apply.md`
- `docs/adr/0282-mailpit-as-the-smtp-development-mail-interceptor.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-mailpit.md`
- `docs/runbooks/configure-mail-platform.md`
- `inventory/group_vars/all.yml`
- `inventory/group_vars/staging.yml`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `collections/ansible_collections/lv3/platform/playbooks/mailpit.yml`
- `collections/ansible_collections/lv3/platform/roles/mailpit_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `playbooks/mailpit.yml`
- `playbooks/services/mailpit.yml`
- `playbooks/mail-platform-verify.yml`
- `collections/ansible_collections/lv3/platform/playbooks/mail-platform-verify.yml`
- `config/ansible-execution-scopes.yaml`
- `config/command-catalog.json`
- `config/data-catalog.json`
- `config/dependency-graph.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/service-capability-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/slo-catalog.json`
- `config/workflow-catalog.json`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/grafana/dashboards/slo-overview.json`
- `Makefile`
- `scripts/generate_platform_vars.py`
- `scripts/validate_repo.sh`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_mailpit_playbook.py`
- `tests/test_mailpit_runtime_role.py`
- `tests/test_mail_platform_verify_playbook.py`
- `config/ansible-role-idempotency.yml`
- `scripts/serverclaw_authz.py`
- `tests/test_serverclaw_authz.py`
- `scripts/remote_exec.sh`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/diagrams/trust-tier-model.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/live-applies/2026-03-30-adr-0282-mailpit-live-apply.json`

## Verification

- `git fetch origin --prune` refreshed this integration worktree and confirmed
  the newest baseline was `origin/main` commit
  `626c1a76b920c12f977b3edc031862cbd22376e8`, which already carried
  repository version `0.177.94` and platform version `0.130.62`.
- Refreshing onto that newer mainline surfaced stale Keycloak SMTP test
  expectations from `origin/main`; commit `65a056f9cd04c04cfad6f39e0ea984b90496721a`
  updated the focused Keycloak role test slice to inherit ADR 0282's
  repo-managed SMTP contract cleanly on the synchronized tree.
- The authoritative exact-main Mailpit replay used committed source
  `ff68cea5fe866e028b25ed41cae7621bc29727a6`, which refreshed canonical truth
  for the merged baseline and preserved repository version `0.177.94` before
  the live replay.
- `uv run --with pytest python -m pytest -q tests/test_mailpit_runtime_role.py tests/test_mailpit_playbook.py tests/test_mail_platform_verify_playbook.py tests/test_keycloak_runtime_role.py`
  passed with `22 passed`, `make syntax-check-mailpit` passed, and
  `ansible-playbook -i inventory/hosts.yml playbooks/mail-platform-verify.yml --private-key .local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e env=staging --syntax-check`
  passed on the synchronized tree before the authoritative replay.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=mailpit env=production`
  succeeded from committed source `ff68cea5fe866e028b25ed41cae7621bc29727a6`
  with final recap
  `docker-runtime-lv3 : ok=115 changed=5 unreachable=0 failed=0 skipped=18 rescued=0 ignored=0`.
- A fresh guest-local Mailpit probe returned `Version=v1.29.5`,
  `Messages=1`, and `SMTPAccepted=10`, and a fresh probe from `monitoring-lv3`
  sent SMTP to `10.10.10.20:1025` and confirmed the captured message through
  `http://10.10.10.20:8025/api/v1/messages`.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python3 scripts/release_manager.py --bump patch ... --dry-run`
  planned release `0.177.95`, and the matching write run prepared release
  `0.177.95` while preserving `platform_version: 0.130.62`.
- Final automation checks also passed on the release tree:
  `make validate`, `make remote-validate`, `make pre-push-gate`, and
  `make check-build-server`, with the validation follow-up migrating the
  refreshed mainline's remaining raw retry loops in
  `scripts/docker_publication_assurance.py` and `scripts/serverclaw_authz.py`
  onto `platform.retry.with_retry`, rerunning the focused Docker publication
  and ServerClaw authorization pytest slices, and keeping the branch-local
  workstream state non-terminal until the final mainline commit so
  `workstream-surfaces` could pass on the branch.
- After the final registry flip back to `status: merged`,
  `./scripts/validate_repo.sh workstream-surfaces` predictably reported
  `branch 'codex/ws-0282-main-merge' maps to terminal workstream 'ws-0282-main-merge'`;
  that is the documented branch-local guard for terminal workstreams on
  non-`main` branches, not a defect in the merged surfaces themselves.

## Outcome

- Release `0.177.95` carries ADR 0282's exact-main replay onto `main`.
- Platform version remains `0.130.62` because Mailpit first became true on
  `0.130.60`; this release integrates that already-live capability onto the
  synchronized repo truth instead of advancing the platform baseline again.
- `receipts/live-applies/2026-03-30-adr-0282-mailpit-mainline-live-apply.json`
  is the canonical exact-main proof for Mailpit from committed source
  `ff68cea5fe866e028b25ed41cae7621bc29727a6`, superseding the earlier
  branch-local receipt while preserving it in the audit trail.
