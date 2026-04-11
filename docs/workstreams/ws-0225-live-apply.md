# Workstream WS-0225: Server-Resident Reconciliation Via Ansible Pull Live Apply

- ADR: [ADR 0225](../adr/0225-server-resident-reconciliation-via-ansible-pull.md)
- Title: Bootstrap a durable Proxmox-host ansible-pull reconcile loop from the merged control repo
- Status: live_applied
- Implemented In Repo Version: 0.177.43
- Live Applied In Platform Version: 0.130.40
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0225-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0225-live-apply`
- Owner: codex
- Depends On: `adr-0143-gitea`, `adr-0165-workflow-idempotency`, `adr-0168-idempotency-ci`, `adr-0224-server-resident-operations-architecture-bundle`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0225-server-resident-reconciliation-via-ansible-pull.md`, `docs/runbooks/server-resident-reconciliation.md`, `playbooks/server-resident-reconciliation.yml`, `collections/ansible_collections/lv3/platform/roles/server_resident_reconciliation/`, `receipts/live-applies/2026-03-28-adr-0225-server-resident-reconciliation-via-ansible-pull-live-apply.json`, `workstreams.yaml`

## Scope

- add a repo-managed host role that bootstraps and maintains a durable `ansible-pull` checkout on `proxmox-host`
- provision a least-privilege Gitea read token for the host-local pull path during the controller-driven bootstrap step only
- install a managed `GIT_ASKPASS` helper, reconcile wrapper, and `systemd` timer on the Proxmox host
- manually trigger the first host-local pull, verify the checkout and receipt flow end to end, and capture branch-local live evidence

## Non-Goals

- migrating every existing service converge into host-local `ansible-pull` in one workstream
- introducing signed release bundles or full event-driven reconcile triggers in the same slice
- updating protected main-integration files before this branch became the final merge step

## Expected Repo Surfaces

- `docs/adr/0225-server-resident-reconciliation-via-ansible-pull.md`
- `docs/workstreams/ws-0225-live-apply.md`
- `docs/runbooks/server-resident-reconciliation.md`
- `playbooks/server-resident-reconciliation.yml`
- `collections/ansible_collections/lv3/platform/roles/server_resident_reconciliation/`
- `tests/test_server_resident_reconciliation.py`
- `receipts/live-applies/2026-03-28-adr-0225-server-resident-reconciliation-via-ansible-pull-live-apply.json`
- `receipts/live-applies/evidence/2026-03-28-adr-0225-*`
- `workstreams.yaml`

## Expected Live Surfaces

- `proxmox-host` carries a managed checkout under `/srv/proxmox-host_server`
- `lv3-server-resident-reconciliation.service` and `.timer` are enabled on the Proxmox host
- the host can pull `ops/proxmox-host_server` from private Gitea with a low-privilege token and converge the local playbook with `ansible-pull`
- each run writes a host-local JSON receipt under `/var/lib/lv3/server-resident-reconciliation/receipts/`

## Verification

- `uv run --with pytest --with pyyaml pytest -q tests/test_server_resident_reconciliation.py` passed with `7 passed in 0.06s`
- `ansible-playbook -i inventory/hosts.yml playbooks/server-resident-reconciliation.yml --syntax-check` passed from the isolated worktree
- `./scripts/validate_repo.sh data-models architecture-fitness generated-docs agent-standards` passed after the ADR index and generated truth surfaces were refreshed
- the first controller-driven bootstrap apply succeeded from `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0225-live-apply` after repairing the Gitea search query and switching service-account token lifecycle calls to basic auth, and the later latest-main replay from source commit `08ef5c90d8df239c3be00ef6b98a4fbb47b26cb4` rendered a dedicated local `ansible-pull` inventory to fix repeated host-local runs
- after rebasing onto the latest `origin/main`, the private Gitea repo published exact snapshot commit `5b121f700d0f1cd372ef85f24288691fb8a88e0c` for source commit `aacd8443b064aa2a14f9929f11a3ae45ae530095`
- on `2026-03-28T17:53:04Z`, `sudo systemctl start lv3-server-resident-reconciliation.service` completed successfully on `proxmox-host`, the managed timer stayed active, `/srv/proxmox-host_server` checked out `5b121f700d0f1cd372ef85f24288691fb8a88e0c`, the working tree stayed clean, and `/var/lib/lv3/server-resident-reconciliation/receipts/latest.json` recorded `status: ok`, `exit_code: 0`, `duration_seconds: 9`, and `inventory_path: /var/lib/lv3/server-resident-reconciliation/ansible-pull-inventory.yml`
- the focused post-flip ADR 0225 checks remained green, and final `make validate` advanced through the repo-wide `ansible-lint` warning baseline before stopping at the expected branch-local workstream surface ownership guard for terminal `live_applied` workstreams

## Outcome

- `proxmox-host` now carries a durable server-resident checkout under `/srv/proxmox-host_server`, a managed `GIT_ASKPASS` helper, and `lv3-server-resident-reconciliation.service` plus `.timer`
- repeated `ansible-pull` replays now use a managed local inventory under `/var/lib/lv3/server-resident-reconciliation/ansible-pull-inventory.yml`, so the checkout step targets `localhost` while the playbook still limits itself to `proxmox-host`
- the bootstrap path now mints or rotates the low-privilege `lv3-reconcile` Gitea read token without leaving the controller-admin artifact on the host after bootstrap
- each host-local run now writes a bounded JSON receipt under `/var/lib/lv3/server-resident-reconciliation/receipts/`, which keeps reconciliation evidence outside the managed git checkout

## Mainline Integration

- release `0.177.43` now carries the official repo-version attribution for ADR 0225 on the latest rebased mainline integration candidate
- the exact rebased candidate source commit `aacd8443b064aa2a14f9929f11a3ae45ae530095` was published to the private Gitea source as `5b121f700d0f1cd372ef85f24288691fb8a88e0c` and replayed successfully on `proxmox-host`, which lifted `versions/stack.yaml` to platform version `0.130.40`
- the protected integration files were finalized after that exact-main replay: `README.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/0.177.43.md`, and `versions/stack.yaml`

## Notes For The Next Assistant

- keep the recurring `ansible-pull` path independent of controller-only admin artifacts after bootstrap
- the host trusts the private Gitea repo rather than GitHub directly, so branch-local verification needs a published internal Gitea snapshot or other approved staging ref before `systemctl start lv3-server-resident-reconciliation.service` can prove the pull path end to end
- `scripts/workstream_surface_ownership.py --validate-branch` is expected to reject this branch once `workstreams.yaml` records the terminal `live_applied` status; the focused ADR 0225 validation slice stays green, and the final `make validate` failure now reflects that branch-only guard after the repo-wide `ansible-lint` warning baseline completes
