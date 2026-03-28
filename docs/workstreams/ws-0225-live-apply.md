# Workstream WS-0225: Server-Resident Reconciliation Via Ansible Pull Live Apply

- ADR: [ADR 0225](../adr/0225-server-resident-reconciliation-via-ansible-pull.md)
- Title: Bootstrap a durable Proxmox-host ansible-pull reconcile loop from the merged control repo
- Status: in-progress
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
- updating protected main-integration files until and unless this branch becomes the final merge step

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

- focused pytest coverage for the new role, templates, and playbook metadata
- `./scripts/validate_repo.sh agent-standards`
- `make validate`
- controller-driven bootstrap apply from the isolated worktree
- manual `systemctl start lv3-server-resident-reconciliation.service` on `proxmox_florin`
- verification of the checkout, timer schedule, journald output, and latest host-local reconcile receipt

## Notes For The Next Assistant

- keep the recurring `ansible-pull` path independent of controller-only admin artifacts after bootstrap
- if the live apply succeeds before main integration, record exactly which protected files still need the final merged-main step
