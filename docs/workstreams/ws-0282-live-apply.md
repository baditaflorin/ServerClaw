# Workstream ws-0282-live-apply: Live Apply ADR 0282 From Latest `origin/main`

- ADR: [ADR 0282](../adr/0282-mailpit-as-the-smtp-development-mail-interceptor.md)
- Title: Deploy Mailpit as the private SMTP development and staging mail interceptor
- Status: ready_for_merge
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: 0.130.60
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0282-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0282-live-apply`
- Owner: codex
- Depends On: `adr-0041`, `adr-0107`, `adr-0165`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0282`, `docs/workstreams/ws-0282-live-apply.md`, `docs/runbooks/configure-mailpit.md`, `docs/runbooks/configure-mail-platform.md`, `inventory/group_vars/all.yml`, `inventory/group_vars/staging.yml`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `playbooks/mailpit.yml`, `playbooks/services/mailpit.yml`, `collections/ansible_collections/lv3/platform/roles/mailpit_runtime/`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`, `playbooks/mail-platform-verify.yml`, `collections/ansible_collections/lv3/platform/playbooks/mail-platform-verify.yml`, `config/*catalog*.json`, `Makefile`, `scripts/generate_platform_vars.py`, `scripts/validate_repo.sh`, `receipts/image-scans/`, `receipts/live-applies/`

## Scope

- deploy Mailpit on the Docker runtime VM as a private guest-network SMTP and HTTP capture service
- add a non-production SMTP override contract so staging automation can target Mailpit instead of Stalwart
- verify the private Mailpit API and SMTP capture path end to end on the live platform
- record branch-local evidence and any exact remaining main-only truth updates clearly

## Non-Goals

- exposing Mailpit on the public NGINX edge or publishing a public subdomain
- replacing Stalwart for production transactional or operator mail delivery
- rewriting protected integration files on this workstream branch before the final verified merge-to-main step

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0282-live-apply.md`
- `docs/adr/0282-mailpit-as-the-smtp-development-mail-interceptor.md`
- `docs/runbooks/configure-mailpit.md`
- `docs/runbooks/configure-mail-platform.md`
- `inventory/group_vars/all.yml`
- `inventory/group_vars/staging.yml`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `playbooks/mailpit.yml`
- `playbooks/services/mailpit.yml`
- `collections/ansible_collections/lv3/platform/playbooks/mailpit.yml`
- `collections/ansible_collections/lv3/platform/roles/mailpit_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
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
- `receipts/image-scans/`
- `receipts/live-applies/`

## Expected Live Surfaces

- `docker-runtime-lv3` listens privately on TCP `1025` for Mailpit SMTP capture
- `docker-runtime-lv3` listens privately on TCP `8025` for the Mailpit UI and REST API
- the Docker runtime guest firewall allows guest-network and management-plane access to those private listeners only
- staging SMTP-aware automation can target `smtp_host: mailpit` on the `dev-tools_default` Docker network instead of Stalwart

## Verification

- `uv run --with pytest python -m pytest -q tests/test_mailpit_runtime_role.py tests/test_mailpit_playbook.py tests/test_keycloak_runtime_role.py tests/test_mail_platform_verify_playbook.py`
- `make syntax-check-mailpit`
- `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0282syntax --playbook playbooks/services/mailpit.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check`
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=mailpit env=production`
- `ansible-playbook -i inventory/hosts.yml playbooks/mail-platform-verify.yml --private-key .local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e env=staging --syntax-check`

## Results

- Branch-local live apply succeeded from commit `ae60394c67d15486f7d64a90b327bac4ad0e7174`.
- Receipt: `receipts/live-applies/2026-03-30-adr-0282-mailpit-live-apply.json`
- The first governed replay exposed a real role-contract bug (`platform service catalog must be a mapping`); commit `ae60394c67d15486f7d64a90b327bac4ad0e7174` repaired the topology lookup and the second replay completed cleanly.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=mailpit env=production` finished with `docker-runtime-lv3 : ok=95 changed=7 unreachable=0 failed=0 skipped=17 rescued=0 ignored=0`.
- Independent post-apply Ansible verification on `docker-runtime-lv3` returned Mailpit info with `Version=v1.29.5`, and a second probe from `monitoring-lv3` sent SMTP to `10.10.10.20:1025` and confirmed one captured message through `http://10.10.10.20:8025/api/v1/messages`.

## Merge-To-Main Notes

- remaining for merge to `main`: update `VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, `build/platform-manifest.json`, and any generated status surfaces only after the exact synchronized mainline integration step is prepared
- the branch-local receipt proves live state and keeps the protected release surfaces deferred until that final mainline closeout
