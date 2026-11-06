# ADR 0494: The agent-history store runs on its own guest with its own Postgres

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-10-28
- Activation: activated on 2026-10-29 by the owner (the `lifecycle: planned` line was deleted; see the activation record); provisioned the same day (the first run's traps are in the runbook, "Provisioning record and traps")

## Context

The agent-history family (a collector, a store, a query CLI and a redaction library) keeps every prompt, reply, tool
call, tool result and bus message of the coding agents that run on the operator laptops in one searchable store. Two
redaction passes run before anything is stored, but the store still holds every secret an agent ever saw, so it is
the most sensitive service on the platform. It needs Postgres 17 with pgvector, 3 to 6 million events for a 30-day
pilot, and grows by about 15 to 30 GB a month once it is widened.

The shared PostgreSQL guests (`postgres`, `postgres-apps`, `postgres-data`) have no pgvector and serve other services,
and the store's own specification says it never shares a database server. The hypervisor was at 12.8 % available memory on
2026-10-28 and at 7.9 % (9.9 GiB) on 2026-10-29 (its placement guard fires below 15 %), about 72 to 82 % CPU, and its
RAID1 arrays have one member (alert `HostMirrorSingleMember`). `make provision-guests` runs `qm set --balloon 0` and the declared hardware on every declared
guest, and the declarations differ from the live guests in several places, so it is not a safe way to add one guest.

## Decision

1. One new guest `agent-history` (vmid 155, 10.10.10.55): 4 vCPU, 8 GiB memory with a 6 GiB balloon floor, a 24 GiB OS
   disk and a 128 GiB data disk, both thin qcow2 on `local`. The data disk is LUKS2, created inside the guest; the
   guest has no swap and ships no logs off the VM (a fragment of a transcript in a central log would defeat the
   encrypted volume). The guest is not added to `guest-log-shipping` on purpose.
2. It runs one compose project: `pgvector/pgvector:0.8.1-pg17` (never published) and the `agent-store` API (bound to
   loopback), behind `tailscale serve`, which terminates TLS. Settings that differ from a default Postgres are in the
   role (`log_error_verbosity=terse`, `shared_buffers`, `max_wal_size`, no `fsync` relaxation).
3. Exposure is operator-only (ADR 0049): the guest is a tailnet node carrying a **new tag, `tag:agent-history`**, and the
   policy grants exact addresses (the four operator Macs and `ubuntuvm1`, 100.64.0.7, the host `0docker_docker` that carries
   the hub's traffic) to `tcp:443` of that tag and nothing else. The policy change is part of this change
   (`config/tailscale/policy.hujson`: the `tagOwners` entry, the one grant and two policy tests); merging does not apply it: a new
   tag is a section change that the CT108 reconciler marks `blocked`, so a human applies it with
   `scripts/tailscale-policy-ct108.sh plan` and then `apply` (the runbook has the order). The enrollment OAuth client can only
   mint `tag:pool-runtime` keys, so `tag:pool-runtime` is a **temporary co-owner** of the new tag: the node enrols with it and
   re-advertises `tag:agent-history`, and a follow-up policy change then removes the co-owner (the same two-step as the 0pipe
   build server). HTTPS certificates are enabled on the tailnet, so `tailscale serve --https` terminates TLS. Nothing is published through public DNS, the edge VM or a hypervisor port
   proxy. The guest firewall accepts the tailnet range on 443 only because the tailnet grant is the narrowing control; the
   guest-policy rule says so.
4. Secrets (database password, read, write and metrics tokens, LUKS passphrase) live in OpenBao and reach the guest as
   tmpfs files under the platform's runtime secret root (`/run/<prefix>-secrets/agent-history/`) through an OpenBao Agent (ADR 0077, ADR 0231). No secret value is in git,
   in a template, in `argv` or in the controller-local store. The role never creates, copies or logs a token: the
   OpenBao administrator creates the KV entries and the AppRole, and the owner types the LUKS passphrase.
5. The guest is covered by the nightly PBS job (`all 1`); a restore drill precedes any widening; the store is
   rebuildable from the laptops' own transcripts (the collector's backfill is idempotent), which is what makes a
   nightly RPO and a single-member RAID1 acceptable for the pilot and not beyond it.
6. Metrics reach the 0mcp Prometheus through the node_exporter textfile collector (`agent_history_*`, written by a
   timer on the guest that reads the store's `/metrics` with the metrics token); the rules live in
   `config/prometheus/rules/agent-history.yml` and are added by a separate change.
7. Provisioning uses a per-guest playbook, `playbooks/agent-history-vm.yml` (`make provision-agent-history-vm`), that
   limits `proxmox_guests_active` to this vmid and asserts it; precedent: `artifact-cache-vm.yml`. The unrestricted
   `make provision-guests` is not used. **The declaration was inert until the owner activated it (done on 2026-10-29, see the
   activation record) and the guard below stays for any guest declared planned.** The guest was declared
   with `lifecycle: planned`: the default guest set of `proxmox-install.yml` (`make provision-guests`, bootstrap) skips
   planned guests (otherwise the guests role would clone VM 155 with 8 GiB onto a host at 7.9 % available memory, because an
   empty `proxmox_guests_active` falls back to every declared guest), the guests role refuses a planned guest in any
   selection, the inventory puts it in the `planned_guests` group (it stays in `lv3_guests` so its group variables still
   apply to its own playbook) and every scoped run and scoped host pattern excludes that group (so `converge-guest-network-policy`
   and the other scoped converges never reach a host that does not exist), and the per-guest playbook refuses to run. The
   owner activates a guest with one reviewed change: delete the `lifecycle: planned` line in
   `inventory/host_vars/proxmox-host.yml` and run `make generate-inventory` (which drops the `planned_guests` membership;
   the group stays emitted, empty). That change is the recorded approval of the capacity decision (decision 8) and carries its
   written exception.
8. Placement: the gate is: no provisioning while the hypervisor's 24-hour minimum of `MemAvailable` is below the guest's firm
   RAM + 5 % of host RAM + 2 GiB (6.3 GiB + 2 GiB for a 6 GiB guest on this host), unless the owner records an exception. The
   route (owner decisions of 2026-10-29): **wait for the migration of CI, build and Woodpecker load to the new `0pipe` server
   (128 GB RAM, 32 cores), and re-measure with `fleet-prom`**. On 2026-10-29 the host was at 7.9 % (9.9 GiB) available, down
   from 12.8 %; then VM 130 (`docker-build-lv3`) was trimmed live from 20 to 10 GiB (balloon floor 10240) and `MemAvailable`
   went from 10.4 to 15.5 GiB (about 12.3 %), which is above the 14.3 GiB of the rule at that instant but is not the
   24-hour minimum, and still below the owner's 15 % placement guard (18.9 GiB). So the 24-hour minimum is re-measured at
   activation time, and **a written exception to the 15 % guard is still required** in the activation change unless the
   migration changes that. The `drop_caches` and the VM 171 and VM 200 trims in the runbook are only a fallback after
   re-measuring, each its own approval right before provisioning with the service impact stated; **VM 180 (CI-critical,
   balloon 0) is never trimmed**. This ADR does not make the decision. Provisioning is run from the
   `platform_server` checkout whose `.local/active-deployment` is `0mcp`.
9. The data volume needs a manual unlock after every reboot of the guest; the compose project starts only when
   `/srv/agent-history` is mounted and the token files exist.

## Consequences

- New isolation and a clean rollback (stop the collectors, revoke the tokens, destroy the guest, prune `vm/155` from the
  PBS datastore), at the price of one more guest on an over-committed host.
- A manual LUKS unlock after each guest reboot, and a restore needs the passphrase from OpenBao.
- The hub's read-token copy lives in a second secret system, with a second rotation step.
- Backups hold ciphertext for the data disk (PBS cannot compress it); the OS disk holds container images and the
  OpenBao Agent's AppRole files (see the accepted trade-offs below).
- The guest was inert until the owner activated it: nothing that provisions or converges guests touched it, at the price of one
  extra key (`lifecycle`) and group (`planned_guests`) in the guest declarations and the inventory generator. **Since the activation
  it is no longer inert, and it does not exist yet**: an unrestricted `make provision-guests` would clone it (and rewrite the hardware
  of every other declared guest), and scoped runs on `lv3_guests` (`converge-guest-network-policy` and the other scoped converges)
  would reach 10.10.10.55 and fail on it. Merge the activation immediately before provisioning, provision only with
  `make provision-agent-history-vm`, and declare the guest `lifecycle: planned` again if provisioning is postponed.
- The image catalog does not list the two images yet: a digest pin and a vulnerability scan need the registry and
  the build host, which this change does not contact. Pinning is a step of provisioning.
- Stale model numbers in `config/capacity-model.json` (host RAM and vCPU) are not corrected here.

## Activation record (2026-10-29)

The owner activated the guest by the change that deleted `lifecycle: planned` from the VM 155 entry (and regenerated
`inventory/hosts.yml`, which keeps the `planned_guests` group, now empty). Capacity at that decision:

- `pve-0mcp` `MemAvailable` was **15.5 GiB (12.3 %) at 09:30Z on 2026-10-29**, after VM 130 (`docker-build-lv3`) was trimmed live from
  20 to 10 GiB (balloon floor 10240); it had been 9.9 GiB (7.9 %) at 07:55Z and 12.8 % the day before. Figures relayed from the
  main agent-history session; the 24-hour minimum was not measured.
- VM 155 needs a **6 GiB balloon floor** (8 GiB maximum). After provisioning the host stays above the 5 % critical line (6.3 GiB):
  15.5 - 6 = 9.5 GiB (7.6 %) at the floor and 7.5 GiB (6.0 %) at the maximum, but **below the owner's 15 % placement guard**
  (18.9 GiB).
- **The written exception to the 15 % guard:** owner decision 2026-10-29, option B plus the VM 130 trim; the store is rebuildable
  from the laptops (idempotent backfill), so a lost or restored-late store costs time, not history.
- Not trimmed: VM 180 (CI-critical, balloon 0). `drop_caches` and the VM 171 and VM 200 trims were not done and stay a fallback.

Activation does not provision anything. It removes the guards that kept the declaration inert, so provisioning is the next
step, with the preconditions in the runbook (the tailnet policy applied, OpenBao prepared by the owner, the encrypted volume).

## Accepted trade-offs (recorded, not changed here)

- **`--allow-discards` on the LUKS volume.** Discards let the thin qcow2 file shrink and let `fstrim` reclaim space, but they
  reveal which blocks of the data disk are in use to anyone who can read the raw disk or the PBS image. Accepted for the pilot.
- **`remove_secret_id_file_after_reading = false` for the OpenBao Agent.** The agent must re-authenticate after every restart
  and reboot, so a static AppRole `secret_id` stays on the OS disk at mode 0400 (owner uid 65532). A copy of the OS disk or of
  the PBS image therefore carries a credential that can read the store's secrets from OpenBao for as long as the secret id
  and the network path to OpenBao are valid. Accepted for the pilot; follow-up: a response-wrapped `secret_id` with a short TTL
  delivered at each start, so no long-lived credential rests on the disk.

- **`tag:pool-runtime` as a temporary co-owner of `tag:agent-history`.** Any node that holds `tag:pool-runtime` can mint or
  advertise the new tag while the entry stands, which would let it present itself as the store to the Macs and the hub. Accepted
  only for the enrolment window; the follow-up policy change that removes the co-owner is a step of the runbook.

## Alternatives rejected

- The shared `postgres-data` guest: no pgvector, shared blast radius, the store's specification forbids it.
- Docker on `docker-runtime`: swap full and load far above its CPU count on 2026-10-28.
- The `artifact-cache` guest: CI-critical, no container DNS.
- Publication through the edge: violates ADR 0049 for the most sensitive service on the platform.
- `proxmox_tailscale_tcp_proxies` on the hypervisor: edits a shared failure domain for a pilot.

## Questions, by the number used in the planning notes

Answered by the owner on 2026-10-29 and reflected here: 1 (capacity: wait for the 0pipe migration and re-measure; option B only as
a fallback; a written exception to the 15 % guard still needed), 4 (a new tag `tag:agent-history`; HTTPS certificates are
enabled on the tailnet), 5 (the hub's traffic reaches the store from `ubuntuvm1`, 100.64.0.7: the grant admits every workload
on that host, so the bearer token is the control that tells the hub from its neighbours), 15 (the
controller is the `platform_server` checkout whose `.local/active-deployment` is `0mcp`; the deployments it knows are
`0mcp` and `lv3`), 16 (alert routing: warning only, no paging, including for a canary leak; the alert rules are a separate change),
14 (embeddings: the model is bge-m3, 1024 dimensions, run by Ollama on a Mac with an Apple GPU, never on the hypervisor; the store embeds
each search question through that Mac and a worker on it fills the vectors with a separate embed token: ws-20261029-agent-history-embed-query).

Still open: 7 (OpenBao AppRole and paths: the owner holds OpenBao admin, so it is a step at provisioning time), 6 (accept a
manual unlock and no swap, no log shipping), 12 (adding the guest to the weekly restore drill), 13 (the pilot's end date and
the decision at the end). The written capacity exception to the 15 % guard is no longer open: it is recorded in the activation record.
18 (whether this ADR records the RAID1 and rebuildable-store assumption) is answered here: it does.
