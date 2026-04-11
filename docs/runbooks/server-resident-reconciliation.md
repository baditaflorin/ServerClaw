# Server-Resident Reconciliation

## Purpose

This runbook defines the ADR 0225 bootstrap and verification path for the
Proxmox host's server-resident `ansible-pull` reconcile loop.

## Canonical Surfaces

- playbook: [playbooks/server-resident-reconciliation.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/server-resident-reconciliation.yml)
- role: [collections/ansible_collections/lv3/platform/roles/server_resident_reconciliation/](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/collections/ansible_collections/lv3/platform/roles/server_resident_reconciliation)
- ADR: [docs/adr/0225-server-resident-reconciliation-via-ansible-pull.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/docs/adr/0225-server-resident-reconciliation-via-ansible-pull.md)

## Bootstrap From A Controller

Run the bootstrap playbook from a controller that has the mirrored Gitea admin
token and the standard Proxmox SSH key:

```bash
ansible-playbook \
  -i inventory/hosts.yml \
  playbooks/server-resident-reconciliation.yml \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e server_resident_reconciliation_bootstrap_gitea_access=true
```

The bootstrap run will:

- ensure the restricted `lv3-reconcile` Gitea user exists
- ensure that user has read-only access to `ops/proxmox-host_server`
- create or recover the mirrored low-privilege Gitea token
- mirror that token to `proxmox-host`
- install the managed checkout path, askpass helper, dedicated local
  `ansible-pull` inventory, wrapper, and systemd timer

## Source Publication

The host-local service pulls only from the private Gitea repository at
`http://100.64.0.1:3009/ops/proxmox-host_server.git`.

- For routine production runs, trigger the service only after the relevant
  merged `main` content has been published into that private repo.
- For branch-local verification before final main integration, publish an
  explicit internal snapshot or staging ref into the private repo first;
  bootstrapping the host alone does not change the source tree that
  `ansible-pull` will fetch.
- For ADR 0224 exact-main verification, publish the validated integration
  candidate into the private Gitea `main`, then confirm that both
  `/srv/proxmox-host_server` and the latest receipt's `source_commit`
  resolve to that published snapshot.

## Verify The Live Host

1. Confirm the managed systemd units exist and the timer is active:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 \
  'sudo systemctl status lv3-server-resident-reconciliation.service --no-pager && sudo systemctl status lv3-server-resident-reconciliation.timer --no-pager'
```

2. Trigger one manual run:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 \
  'sudo systemctl start lv3-server-resident-reconciliation.service'
```

3. Confirm the checkout, latest commit, clean working tree, and latest
   host-local receipt:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 \
  'sudo git -C /srv/proxmox-host_server rev-parse HEAD && echo --- && sudo git -C /srv/proxmox-host_server status --short && echo --- && sudo cat /var/lib/lv3/server-resident-reconciliation/receipts/latest.json'
```

4. Inspect the journal when a run fails:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 \
  'sudo journalctl -u lv3-server-resident-reconciliation.service -n 200 --no-pager'
```

## Recovery Notes

- If `/etc/lv3/server-resident-reconciliation/gitea-read-token` is missing or
  invalid, rerun the bootstrap command with
  `server_resident_reconciliation_bootstrap_gitea_access=true`.
- Recurring host-local runs do not require the controller-side Gitea admin
  token; that admin token is only needed to mint or recover the low-privilege
  read token during bootstrap.
- The recurring wrapper now uses the managed local inventory
  `/var/lib/lv3/server-resident-reconciliation/ansible-pull-inventory.yml`
  instead of the repo inventory, which lets `ansible-pull` complete its own
  checkout step through `localhost` while the playbook still limits itself to
  the durable `proxmox-host` alias.
- The host-local receipts live under
  `/var/lib/lv3/server-resident-reconciliation/receipts/` so the git checkout
  stays clean between timer runs.
- Gitea 1.25.5 accepts admin-token auth for user lifecycle calls, but the
  service-account access-token endpoints require basic auth as that restricted
  user. The bootstrap flow therefore resets the restricted user's password only
  when it needs to mint or rotate the mirrored read token.
