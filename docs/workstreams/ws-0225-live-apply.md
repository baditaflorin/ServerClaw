# Workstream WS-0225: Server-Resident Reconciliation Via Ansible Pull Live Apply

- ADR: [ADR 0225](../adr/0225-server-resident-reconciliation-via-ansible-pull.md)
- Title: Bootstrap a durable Proxmox-host ansible-pull reconcile loop from the merged control repo
- Status: live_applied
- Implemented In Repo Version: 0.177.41
- Live Applied In Platform Version: 0.130.39
- Implemented On: 2026-03-28
- Live Applied On: 2026-03-28
- Branch: `codex/ws-0225-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0225-live-apply`
- Owner: codex
- Depends On: `adr-0143-gitea`, `adr-0165-workflow-idempotency`, `adr-0168-idempotency-ci`, `adr-0224-server-resident-operations-architecture-bundle`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0225-server-resident-reconciliation-via-ansible-pull.md`, `docs/runbooks/server-resident-reconciliation.md`, `playbooks/server-resident-reconciliation.yml`, `collections/ansible_collections/lv3/platform/roles/server_resident_reconciliation/`, `receipts/live-applies/2026-03-28-adr-0225-server-resident-reconciliation-via-ansible-pull-live-apply.json`, `workstreams.yaml`

## Scope

- add a repo-managed host role that bootstraps and maintains a durable `ansible-pull` checkout on `proxmox_florin`
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

- `proxmox_florin` carries a managed checkout under `/srv/proxmox_florin_server`
- `lv3-server-resident-reconciliation.service` and `.timer` are enabled on the Proxmox host
- the host can pull `ops/proxmox_florin_server` from private Gitea with a low-privilege token and converge the local playbook with `ansible-pull`
- each run writes a host-local JSON receipt under `/var/lib/lv3/server-resident-reconciliation/receipts/`

## Verification

- `uv run --with pytest --with pyyaml pytest -q tests/test_server_resident_reconciliation.py` passed with `6 passed in 0.06s`
- `ansible-playbook -i inventory/hosts.yml playbooks/server-resident-reconciliation.yml --syntax-check` passed from the isolated worktree
- `./scripts/validate_repo.sh agent-standards` passed before the final terminal workstream status flip
- controller-driven bootstrap apply succeeded from `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0225-live-apply` after repairing the Gitea search query and switching service-account token lifecycle calls to basic auth
- the private Gitea repo published synthetic snapshot commit `488c6656b1bae1b5ddede2163f1e395f2126483a` for source commit `b8d2aaf0da18dea9dbab286377006b93459b2ac3`
- `sudo systemctl start lv3-server-resident-reconciliation.service` completed successfully on `proxmox_florin`, the managed timer stayed active, `/srv/proxmox_florin_server` checked out `488c6656b1bae1b5ddede2163f1e395f2126483a`, and `/var/lib/lv3/server-resident-reconciliation/receipts/latest.json` recorded `status: ok`
- the focused post-flip ADR 0225 checks remained green, while full `make validate` still hit pre-existing `ansible-lint` warnings outside ADR 0225

## Outcome

- `proxmox_florin` now carries a durable server-resident checkout under `/srv/proxmox_florin_server`, a managed `GIT_ASKPASS` helper, and `lv3-server-resident-reconciliation.service` plus `.timer`
- the bootstrap path now mints or rotates the low-privilege `lv3-reconcile` Gitea read token without leaving the controller-admin artifact on the host after bootstrap
- each host-local run now writes a bounded JSON receipt under `/var/lib/lv3/server-resident-reconciliation/receipts/`, which keeps reconciliation evidence outside the managed git checkout

## Mainline Integration

- release `0.177.41` now carries the official repo-version attribution for ADR 0225 on `main`
- the integrated canonical truth now records `versions/stack.yaml` repo version `0.177.41`, platform version `0.130.39`, and capability receipt `server_resident_reconciliation: 2026-03-28-adr-0225-server-resident-reconciliation-via-ansible-pull-live-apply`
- this workstream became the final verified integration step, so the protected integration files were updated on the same branch after live verification: `README.md`, `VERSION`, `changelog.md`, `docs/release-notes/README.md`, `docs/release-notes/0.177.41.md`, and `versions/stack.yaml`

## Notes For The Next Assistant

- keep the recurring `ansible-pull` path independent of controller-only admin artifacts after bootstrap
- the host trusts the private Gitea repo rather than GitHub directly, so branch-local verification needs a published internal Gitea snapshot or other approved staging ref before `systemctl start lv3-server-resident-reconciliation.service` can prove the pull path end to end
- `make validate` passed while this branch still mapped to an active workstream; after the final `workstreams.yaml` flip to terminal `live_applied`, `scripts/workstream_surface_ownership.py --validate-branch` is expected to reject the branch by design
