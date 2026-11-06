# Configure the agent-history VM

## Purpose

ADR 0494: provision `agent-history` as VM `155` (10.10.10.55), converge the store runtime on it, and run it with an
encrypted data volume, secrets delivered by OpenBao, and no exposure beyond the tailnet.

VM 155 was provisioned on 2026-10-29 and the store answers over the tailnet. The sections "Preconditions" and "Provision" are the plan
as written before that run; "Provisioning record and traps (first run, 2026-10-29)" holds the invocation that worked and every trap met
on the first run (one of them cost the guest its first boot and is fixed in the play, ws-0539). Every step that touches a host is a
separate approval by the owner, with its own rollback.

## Model Summary

- one guest: 4 vCPU, 8 GiB memory with a 6 GiB balloon floor, a 24 GiB OS disk and a 128 GiB data disk (both thin qcow2 on `local`)
- compose project `agent-history`: `pgvector/pgvector:0.8.1-pg17` (never published), `agent-store` (loopback only) and an OpenBao Agent that renders the secret files
- the guest is a tailnet node; `tailscale serve --https=443` proxies to the loopback listener; the tailnet policy names who may reach `tcp:443`
- the data disk is LUKS2, created inside the guest by the owner; the store starts only while `/srv/agent-history` is mounted
- no swap, no log shipping, no public DNS, no edge vhost, no API gateway route, no hypervisor port proxy
- backups: the nightly PBS job `all 1` holds ciphertext; the store is rebuildable from the laptops' transcripts (idempotent backfill)

## Why a separate playbook and make target

`make provision-guests` runs `qm set ... --balloon 0` on every declared guest and the declarations differ from the live guests.
`make provision-agent-history-vm` runs `playbooks/agent-history-vm.yml`, which limits `proxmox_guests_active` to vmid 155 and
fails if it holds anything else (precedent: `playbooks/artifact-cache-vm.yml`).

**The declaration was inert until the owner activated it, and VM 155 has been activated (2026-10-29).** It was declared with
`lifecycle: planned`. Because the guests role treats an empty guest list as "every declared guest", the default set of
`make provision-guests` and the bootstrap targets (`playbooks/proxmox-install.yml`) skips planned guests, the role itself refuses a
planned guest in any selection, the inventory puts a planned guest in `planned_guests` and every scoped run and pattern
(`converge-guest-network-policy` and the other scoped converges) excludes that group, and `make provision-agent-history-vm` refuses a
planned guest. Those guards stay for any guest declared planned; VM 155 no longer is.

## Activation (done on 2026-10-29: the owner's switch)

The change that deleted the `lifecycle: planned` line of the VM 155 entry in `inventory/host_vars/proxmox-host.yml` and ran
`make generate-inventory` (the generated `inventory/hosts.yml` keeps the `planned_guests` group, now empty; the guest stays in
`lv3_guests`) is the recorded approval, and its description carries the capacity record: `pve-0mcp` `MemAvailable` 15.5 GiB (12.3 %)
at 09:30Z on 2026-10-29 after VM 130 was trimmed from 20 to 10 GiB; VM 155 needs a 6 GiB floor, so the host stays above the 5 % critical
line (6.3 GiB) and below the owner's 15 % guard; the written exception to that guard is "owner decision 2026-10-29, option B plus the VM 130
trim; the store is rebuildable from the laptops" (ADR 0494, activation record).

**Since the activation the guest is no longer inert, and it does not exist yet.** An unrestricted `make provision-guests` would clone it and
rewrite the hardware of every other declared guest, and scoped runs on `lv3_guests` (`converge-guest-network-policy` and the other scoped
converges) reach 10.10.10.55 and fail on it. So: merge the activation change immediately before provisioning, provision only with
`make provision-agent-history-vm`, and declare the guest `lifecycle: planned` again if provisioning is postponed. After provisioning, a later
change sets the guest's `status` in `config/capacity-model.json` from `planned` to `active`.

## Preconditions (each needs the owner)

1. **Capacity (owner decisions of 2026-10-29).** Stay on this hypervisor. **Wait for the migration of CI, build and Woodpecker load to the new `0pipe` server (128 GB RAM, 32 cores) and re-measure with `fleet-prom`:** the rule is that the 24-hour minimum of `MemAvailable` is at least the guest's firm RAM + 6.3 GiB (5 % of host RAM) + 2 GiB, i.e. 14.3 GiB for a 6 GiB guest (the 6 GiB floor, 8 GiB maximum). On 2026-10-29 the host was at 9.9 GiB (7.9 %) available, down from 16.1 GiB (12.8 %) the day before; then VM 130 (`docker-build-lv3`) was **trimmed live from 20 to 10 GiB (balloon floor 10240)** and `MemAvailable` went from 10.4 to 15.5 GiB (about 12.3 %). That is above 14.3 GiB at that instant but it is not the 24-hour minimum, and it is below the owner's 15 % placement guard (18.9 GiB): **re-measure over a full 24 hours at activation time (these numbers move), and a written exception to the 15 % guard goes in the activation change unless the migration changes that.** `drop_caches` and the VM 171 and VM 200 trims below are **only a fallback if the re-measured rule still fails**, each its own yes from the owner right before provisioning and never earlier, with the service impact stated first. The fallback ends near 12.5 % available after a 6 GiB guest from the earlier readings, so it does not replace the exception. Fallback steps:
   1. `sync; echo 2 > /proc/sys/vm/drop_caches` on the hypervisor (documented, needs no undo). Read `node_memory_MemAvailable_bytes` before and after: the relief (about 8.5 GiB if the earlier figure still holds) comes from the kernel's shrinkers, not from slab (`SReclaimable` is only about 0.23 GB), so it must be measured, not assumed.
   2. VM 171 (`coolify-apps-lv3`): `qm set 171 --balloon 5120`. Its balloon floor is 7168 MiB with `memory: 8192` and memory hotplug on, so lowering the floor frees about 2 GiB live with no restart. Rollback: `qm set 171 --balloon 7168`.
   3. Re-measure.
   4. Only if still short: VM 200 (`0mcp-staging-runtime`, 4 GiB, balloon 0) to 2.5 GiB, which needs a restart (staging) and frees about 1.5 GiB.
   5. The written exception to the 15 % guard, if it is still needed.

   **VM 180 (`artifact-cache-lv3`, balloon 0) is CI-critical and the VM the agent sessions use for benchmarks: it is never trimmed.** This runbook does not decide capacity.
2. **OpenBao.** TODO(ADR 0494 question 7): the owner holds OpenBao admin, so this is a step at provisioning time, before the guest is started: the administrator creates the KV entry `kv/services/agent-history/runtime` (the path is a role variable, `agent_history_openbao_kv_path`) with four keys:
   - `db_password`: hex or base64url, no character that needs URL escaping
   - `read_tokens`: one `name=token` per line (for example the hub and each person)
   - `write_tokens`: one `host=token` per line, or two `host:label=token` while a host rotates
   - `metrics_token`: one bare token (the metrics bridge reads `/metrics` with it and can read nothing else)

   plus a policy that allows `read` on exactly that data path, and an AppRole bound to it. Tokens are at least 16 characters (`openssl rand -hex 24`), created by the administrator, and never typed into a chat, an argument, a URL or a transcript. A token for a laptop is put into that laptop's keychain by that laptop's owner.
3. **Network policy.** The guest firewall comes from `network_policy.guests.agent-history`; `runtime-control` allows `tcp 8201` from the guest (TODO question 7: confirm which guest owns OpenBao and its port). `config/network-policy/0mcp.yaml` carries the same flows for the netpolicy drift check.
4. **Images.** `agent-store` is built on a build host (never on a laptop) and loaded with `docker save | gzip | ssh <guest> docker load`. The Postgres image is pulled through the artifact cache. Neither is in `config/image-catalog.json` yet: a digest pin and a vulnerability scan need the registry and the build host and are part of provisioning. Set `agent_history_store_image` to the loaded reference.
5. **Tailnet (decided 2026-10-29; the policy change is in this pull request).** The guest joins as a node carrying a **new tag, `tag:agent-history`**. `config/tailscale/policy.hujson` now has: the `tagOwners` entry (`group:admins` plus a **temporary** `tag:pool-runtime`, because the enrollment OAuth client can only mint `tag:pool-runtime` keys: the node enrols with that tag and re-advertises `tag:agent-history`, as for the 0pipe build server in #602 and #603), the one grant (the four operator Macs and `ubuntuvm1`, 100.64.0.7, the host `0docker_docker` that carries the hub's traffic, to `tag:agent-history`, `tcp:443`, by exact address) and two policy tests (accept 443; deny 22, 5432, 8080 and 9100). Merging does not apply it: a new tag is a section change that the CT108 reconciler marks `blocked`, so after the merge a human runs `scripts/tailscale-policy-ct108.sh plan` and then `apply` (the reconciler's own `classify`, run offline on this change against the previous policy, returns `blocked`: `section tagOwners differs`). The main agent-history session reported a `plan` of this policy against the live tailnet as valid with the policy tests passing (I did not run it). HTTPS certificates are enabled on the tailnet, so `tailscale serve --https` is allowed. The owner mints a single-use auth key (1 hour) for the enrolment tag; no agent and no role sees it.
6. **Policy applied BEFORE provisioning, then the co-owner removed.** The guest's `tcp 443` rule opens the tailnet range and relies on the grant to narrow it, so apply the policy (precondition 5) before the activation change. Once the node carries `tag:agent-history`, a follow-up policy change (ws-0538, its own pull request, applied by a human with `scripts/tailscale-policy-ct108.sh`) **removes `tag:pool-runtime` from the `tag:agent-history` owners** (until it is applied any `tag:pool-runtime` node can present itself as the store; check `config/tailscale/policy.hujson` and the live policy for the current state). The grant admits every workload on `ubuntuvm1`, not only the hub container: the read and write tokens are what tell the hub from its neighbours.
7. **Controller (decided 2026-10-29).** Run the play from a `platform_server` checkout whose `.local/active-deployment` is `0mcp` (the deployments it knows are `0mcp` and `lv3`). A fresh worktree off `main` works too: `.local` is resolved through `scripts/resolve_local_overlay_root.sh` and shared with the main checkout (the first run, on 2026-10-29, used one); an explicit `PLATFORM_INVENTORY_OVERLAY` is needed either way (see the record below).

## Provision (owner approves each step)

1. With the activation change merged (and the other preconditions met), take the deploy lease and run the play:

   ```bash
   make provision-agent-history-vm env=production
   ```

   First check with `--list-tasks` that `proxmox_guests_active` has one entry. The play clones the template, attaches `scsi1`, sets the balloon floor and the discard option, and runs the guest baseline (firewall, access, Docker, the role). The role is safe while the volume is still locked: it prepares everything and reports why it does not start the stack.
2. Create the encrypted volume (the role never formats a disk). On the guest, as the owner, with the passphrase created in OpenBao and never written to disk:

   ```bash
   # the passphrase arrives on standard input, without a trailing newline
   <passphrase source> | sudo cryptsetup luksFormat --type luks2 --key-file=- /dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi1
   <passphrase source> | sudo cryptsetup open --type luks2 --allow-discards --key-file=- /dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi1 agent-history-data
   sudo mkfs.ext4 -L agent-history /dev/mapper/agent-history-data
   sudo cryptsetup close agent-history-data
   ```

   Confirm the device path with `ls -l /dev/disk/by-id/ | grep scsi1` first; a wrong device is data loss.
3. Deliver the AppRole files (owner, over ssh, never in a transcript): `/opt/agent-history/openbao/role_id` and `secret_id`. The role sets them to the OpenBao Agent's uid, mode 0400, and never reads them.
4. Join the tailnet with the one-time key for the enrolment tag `tag:pool-runtime` (the owner types it; never in a transcript), then re-advertise as `tailscale up --hostname agent-history --advertise-tags tag:agent-history`, after the policy of precondition 5 is applied. Then re-run the play so the role publishes `tailscale serve --https` (certificates are enabled on the tailnet), and make the follow-up policy change of precondition 6.
5. Unlock and start: pipe the passphrase into `/usr/local/sbin/agent-history-unlock` over ssh. It opens the volume, mounts it, creates the Postgres directory and starts `agent-history.service`. After every reboot of the guest the volume is locked and the stack is down until this step is repeated.
6. Verify (the role's `verify.yml` runs these when it starts the stack): `GET /healthz` on loopback answers 200, the store listens on `127.0.0.1` only, nothing listens on 5432, the secret files are `0400` owned by uid 65532, the Postgres directory is on `/dev/mapper/agent-history-data`, and there is no swap.
7. First backup: wait for 02:00 or, with approval, one `vzdump 155 --storage own-pbs --mode snapshot`; the PBS group `vm/155` must exist before any stale-backup alert can fire.

## Provisioning record and traps (first run, 2026-10-29)

### The invocation that worked

Run from a fresh worktree off `main`. The committed inventory carries placeholder addresses (RFC 5737, `203.0.113.x`) and the
`proxmox_network` role refuses them on purpose (it would otherwise write a placeholder into the host's network configuration), so the
real hypervisor address and port come from an overlay inventory under `.local`, which is never committed:

```bash
LV3_PROXMOX_HOST_ADDR=<hypervisor public address> LV3_PROXMOX_HOST_PORT=<hypervisor ssh port> \
PLATFORM_INVENTORY_OVERLAY=<overlay inventory file under .local> \
make provision-agent-history-vm env=production \
  BOOTSTRAP_KEY="<absolute path of .local/ssh/bootstrap.id_ed25519> -e agent_history_store_image=agent-store:<version> -e @<absolute path of .local/deployments/0mcp/identity.yml>"
```

`BOOTSTRAP_KEY` is only a way to pass extra `-e` arguments through the make target (the key path comes first). The overlay file:

```yaml
all:
  children:
    proxmox_hosts:
      hosts:
        proxmox-host:
          ansible_host: <hypervisor public address>
          ansible_port: <hypervisor ssh port>
    lv3_guests:
      vars:
        proxmox_guest_ssh_connection_mode: proxmox_host_jump
```

The image is the `agent-store` tarball loaded into the guest beforehand (precondition 4); the play only references it.

### Upgrading the store image (done by hand on 2026-11-02, 0.3.0 to 0.3.1)

`agent_history_store_image` is only ever passed with `-e` (the role default is empty), so **a later play run must pass the version that is
live, `agent-store:0.3.1`, or it renders the compose file back to whatever it is given**. The store's image is changed without touching
Postgres or the LUKS volume (nothing to unlock):

1. Build on a build host: `docker build --build-arg VERSION=<v> --build-arg COMMIT=<sha> -t agent-store:<v> .` from a `git archive` of
   `main` (`release.sh agent-store <v>` in `agent-history-release` does this and exports the tarball), then `docker save | gzip`.
2. Reach the guest through the hypervisor as jump host: `ssh -J operator-bastion ops@10.10.10.55` with `.local/ssh/bootstrap.id_ed25519`.
   The guest's host key is not in `lv3.known_hosts`; read it from inside with `qm guest exec 155 -- cat /etc/ssh/ssh_host_ed25519_key.pub`
   on the hypervisor and compare it with `ssh-keyscan` before trusting it.
3. `docker load` the tarball on the guest, copy `/opt/agent-history/docker-compose.yml` to `docker-compose.yml.bak-<old>`, set the `store`
   image tag, and run `docker compose --file /opt/agent-history/docker-compose.yml up --detach --no-deps store`; wait for `healthy`.
4. Roll back by restoring the backup file and running the same `up` command (the previous image stays loaded).

0.3.1 serves `title` on every hit and timeline event (contract v0.2.3).

### Traps, in the order they were met

1. **The play hard-stopped the VM seconds after the first start (fixed by ws-0539).** The old play applied the balloon floor and the data
   disk's `discard=on` with `qm set` and then ran `qm stop --skiplock 1`, which cut cloud-init's first boot off: zero-byte netplan,
   ssh host keys and apt lists plus a saved `instance-id`, so the next boot saw the same instance (`new=False`) and never configured the
   network. The play now applies the balloon floor live and restarts the VM (graceful `qm shutdown`) only after `cloud-init status --wait`,
   and only when `qm config` differs from `qm config --current 1`. To rescue a guest that an old version of the play already cut off: stop
   the VM, attach its `scsi0` qcow2 on the hypervisor with `qemu-nbd -c /dev/nbd0 <qcow2>` (the partition holding `/` shows in `lsblk`), mount
   it, delete `var/lib/cloud/instance`, `var/lib/cloud/instances/*` and `var/lib/cloud/sem/*` and, under `var/lib/cloud/data/`,
   `instance-id`, `previous-instance-id`, `result.json` and `status.json`, regenerate the ssh host keys under `etc/ssh`, unmount, detach with
   `qemu-nbd -d /dev/nbd0`, and start the VM. The detach prints I/O errors for `nbd0`; they fire `KernelStorageHardwareErrors`, a false alarm.
2. **`apt-get update` right after a cut-off boot can leave empty lists.** Run `rm -rf /var/lib/apt/lists/*` first.
3. **The guest has no `tailscale` (the role does not install it).** Install it from the official apt repository, then enrol: mint a one-time
   `tag:pool-runtime` key with the vault's `tailscale_enroll_oauth_client` on the builder CT108 (the key description takes letters, digits and
   hyphens only), run `tailscale up --auth-key=file:<key file> --advertise-tags=tag:pool-runtime`, then **Tailnet Lock**: sign the node with
   `tailscale lock sign nodekey:... tlpub:...` on a trusted node, and re-advertise with
   `tailscale up --hostname agent-history --advertise-tags=tag:agent-history` (this needs the temporary `tag:pool-runtime` owner entry of
   precondition 6; ws-0538 removes it afterwards). No key value is ever typed into a chat or a transcript.
4. **OpenBao runs on `runtime-control` (port 8201, reached over the bridge) and needs two firewall layers.** The guest nft rule comes from
   `playbooks/guest-network-policy.yml --limit runtime-control -e proxmox_guest_ssh_connection_mode=proxmox_host_jump` (look at the check and
   diff run first). The hypervisor's per-VM firewall file `/etc/pve/firewall/192.fw` is rendered only by the `proxmox_network` role, which is the
   *first* play of that same playbook (`hosts: proxmox_hosts`) and which `--limit runtime-control` therefore skips. A full run replays the whole
   hypervisor network (bridges, nftables, forwarding, every VM's firewall file) and refuses the committed placeholder addresses, so **never run
   that role to change one firewall rule.** On 2026-10-29 the one missing line was appended by hand to `/etc/pve/firewall/192.fw`:
   `IN ACCEPT -source 10.10.10.55/32 -p tcp -dport 8201`. It is declared (`network_policy.guests.runtime-control`, source `agent-history`,
   tcp 8201) and `vm.fw.j2` renders exactly that line, so the next full `proxmox_network` run keeps it. A run may move the manual line to its place in the
   file (expected, not drift). The store does **not** appear in any `all_guests` expansion: its entry carries `network_policy_all_guests: false`, so
   the six ports that rule set opens to every guest (1587, 4222, 8081, 8083, 8098 and 9080) are not opened to it, in the Proxmox files or in any
   guest's nftables (before that flag existed, a re-render of `runtime-control` did add them, and `netpolicy.py drift` reported them as extra). To render only the per-VM files, run the playbook with `--tags proxmox-vm-firewall` (ws-0541): see
   "Render only the per-VM Proxmox firewall files" in `docs/runbooks/configure-guest-network-policy.md` for the command, what it leaves alone and its caveats.
   Use that instead of a hand edit, but read its diff first: the run compares with the live `192.fw` and, since ws-20261030, refuses (nothing written) while that file holds a line the render lacks, which on 0mcp includes hand-added accepts such as the Prometheus 9100 scrape; limit it with `-e proxmox_network_firewall_vmids=<vmid>` and see "The install guard" in that runbook.
   The OpenBao Agent backs off exponentially after failures: `docker restart agent-history-openbao-agent` once the network is fixed.
5. **A new cloud-init instance re-runs `packages`, which failed on `docker.io` against Docker CE (fixed by ws-0539).** A seed change (for example the
   identity overlay changing the domain) creates a new instance. The `docker_runtime` role converges Docker CE and removes `docker.io` as a
   conflicting package, so the guest no longer lists `docker.io` in its cloud-init packages. On a guest already hit, one normal reboot makes
   `cloud-init status` `done`.
6. **The play's Docker converge can drop loaded images.** Reload the `agent-store` tarball afterwards (`docker save | gzip | ssh <guest> docker load`).
7. **After every reboot the LUKS volume is locked.** Unlock with the passphrase on standard input (step 5 of "Provision"); the stack is down until then.

## The redaction canary (daily, unattended)

The store holds every secret an agent ever saw, and redaction is a safety net, not a guarantee. The canary is the test that keeps running: every day fake secrets of every redaction rule are written into fake Claude and Codex session files, shipped by a real collector, stored, and looked for. A hit anywhere means a rule or a stage leaked. Owner decision (2026-10-29): a leak is a `warning`, nothing is paged.

Three parts, each with a different view of the data:

| Part | Where | What it sees |
|---|---|---|
| `agent-eval canary run` (launchd, daily) | a laptop | the pipeline end to end through the store's API: every fake arrived, every rule's placeholder is there, no fake in any field the API returns. Its metrics go to a local textfile only. |
| a second `agent-tail` (launchd, always on) | the same laptop | ships the canary files under the host `canary-<mac>`, with its own `--home`, `--spool` and write token. The same binary as the laptop's real collector, so it tests that build's redaction. |
| `agent-history-canary-scan.timer` (this role, nightly) | the guest | the database itself, including `raw`, which the API never shows. It is the only writer of the `agent_history_canary_*` series in Prometheus (label `source="dbscan"`). |

**The dedicated host.** Write tokens are per host, so the canary collector gets its own: a line `canary-<mac>=<token>` appended to `write_tokens` in the OpenBao entry (never touch another host's line). The OpenBao Agent renders the file within five minutes (`static_secret_render_interval`); then `docker kill -s HUP agent-history-store` makes the store re-read it (log line `tokens reloaded`, `added: write:canary-<mac>`). The role requires the scan host to start with `canary-`, so the scan can never count a real laptop's history. The laptop's keychain holds the write token and a read token (service names `agent-eval-canary-write-token` and `agent-eval-canary-read-token`); neither is ever in an argument list or a file.

**The SQL file.** `agent_history_canary_scan_sql_file` (default `/var/lib/agent-history/canary-scan.sql`, root:root 0600) is printed by agent-eval's `scripts/dbscan` for the canary host and delivered by the owner. It holds the canary's fake secrets (not real ones) and is never committed:

```sh
go run ./scripts/dbscan -maxAge 36h canary-<mac> > canary-scan.sql     # on a build host, not a laptop
scp canary-scan.sql <guest>:/tmp/ && ssh <guest> 'sudo install -m 0600 -o root -g root /tmp/canary-scan.sql /var/lib/agent-history/canary-scan.sql && rm /tmp/canary-scan.sql'
```

It must come from the same agent-redact version as the `agent-eval` binary that generates the canary (a newer rule has a new fake): regenerate and redeliver it whenever the laptop's `agent-eval` is upgraded.

**Why `-maxAge`.** The scan reads one row, `events (all)`, to tell "no leak" from "nothing to look at". Without a window it counts every event the host ever had, so a laptop job that silently died would keep passing on old rows for ever. With `-maxAge 36h` it counts only events the store received in the last 36 hours; leak statements always cover all history.

**What the scan reports** (`agent_history_canary_last_exit_code`):

| Exit | Meaning | Effect |
|---|---|---|
| 0 | the canary is in the database (received within the window) and no fake secret is in any column | `..._last_success_timestamp_seconds` is set to now; `AgentHistoryCanaryMissing` stops being true |
| 1 | a fake secret is in `raw`, `content`, `command` or a title | `agent_history_canary_leaks` > 0: `AgentHistoryCanaryLeak` (warning, no delay). Stop the collectors that run the old redaction, fix the rule, purge the canary rows, rotate anything that matched in real history. |
| 3 | no canary event was received within the window (the laptop job or its collector stopped) | last success stops moving: `AgentHistoryCanaryStale` after 36 hours plus one |
| 4 | psql could not run | previous values are kept: not being able to look never clears an alarm |

**Proving it.** Both directions can be shown without touching the real data path: (a) leak: insert one throwaway row into `events` under the canary host (own native session id starting `canary-leakproof-`) whose `content` holds a canary fake, run `systemctl start agent-history-canary-scan`, see `agent_history_canary_leaks` >= 1 in the textfile and the warning in Prometheus, delete the row by its session id, run the scan again and see 0; (b) not delivered: run the same SQL with a one-second `-maxAge` by hand and see `events (all)` 0 (the scan would exit 3 and leave the last success alone).

**Purging.** The canary rows stay until purged (there is no delete endpoint): `agent-eval canary purge --host canary-<mac>` prints the SQL for the guest's database (it is scoped to the canary host and to native ids starting `canary-`). There is no automatic retention yet.

## Semantic search: the embeddings Mac (ws-20261029-agent-history-embed-query)

Two halves, both off until set up: the store embeds each search **question** at query time, and a worker fills the **vectors** of the stored
prompts, replies and bus messages. Both use the model `bge-m3` (1024 dimensions, the store's `vector(1024)` column), and the store's
`-embedModel` must equal the worker's `--storeModel` (default `--embedModel`) or semantic search finds nothing.

- **Where it runs.** On a Mac with an Apple GPU (mac14 first), never on the hypervisor (a CPU run over about a million passages takes days).
  Two Ollama processes run as launchd user agents, both bound to loopback only: `org.baditaflorin.ollama` on `127.0.0.1:11434` for the
  worker's bulk batches and `org.baditaflorin.ollama-query` on `127.0.0.1:11435` for the store's questions (same model files, `OLLAMA_KEEP_ALIVE=24h`).
  `org.baditaflorin.agent-embed` is a third agent that reads the embed token from the login keychain (`security -i`, never argv) and talks to
  11434. None opens a port to the network. **Why two Ollama processes:** one Ollama serves requests in arrival order, so a search question
  waited behind the worker's 32-text batch: measured 2026-10-29 with the worker running, a question took p50 0.17 s but p90 3.8 s (8 of 30
  over the store's 2 s budget, so `hybrid` fell back to text). Batch 8 brought p90 to 1.1 s but cost a third of the throughput (8.6 events/s);
  a separate process for questions gives p50 0.16 s, p90 0.18 s, max 0.83 s (60 questions) while the worker keeps its full speed.
- **How the VM reaches it.** `tailscale serve --bg --tcp=8443 tcp://127.0.0.1:11435` on the Mac forwards the tailnet address's port 8443 to
  the question instance of Ollama (the policy comment still names 11434, the bulk instance: the opening is the same single tailnet port), and one grant opens exactly that port: `tag:agent-history` to the Mac's `/32`, `tcp:8443` (policy tests deny every other port of
  that Mac and the other Macs). **Why plain http by the Mac's tailnet IP, not https by name:** Ollama answers 403 to any Host header that is
  not loopback, one of its own addresses or `.local`, and `tailscale serve` cannot rewrite the Host header, so `https://<magicdns-name>` is
  refused (tested 2026-10-29); the guest also cannot resolve MagicDNS names. The traffic is inside the WireGuard tunnel between two signed
  nodes and behind the grant, so TLS would add a second layer, not the first. An IP literal also needs no `extra_hosts` pin.
- **Embed token.** `embed_tokens` is a key of the OpenBao entry `kv/services/agent-history/runtime` (one token, at least 16 characters, no
  `,`, `=` or whitespace). The OpenBao Agent renders it to `embed-token`; the store gets `-embedTokenFile`, which is valid for `/v1/embed/*`
  and nothing else. The key must exist **before** the role is applied: the agent renders with `error_on_missing_key`, so a missing key keeps
  the store from starting. Add it with a check-and-set write that leaves the other keys alone; put the same value in the Mac's login keychain
  item `agent-embed-token`.
- **Turn it on.** `agent_history_embed_url: "http://<the Mac's tailnet IP>:8443"` and `agent_history_embed_model: "bge-m3"` are set in
  `inventory/host_vars/agent-history.yml` (committed, so that no later converge drops the flags; the IP is already in the tailnet policy), then run
  the provisioning command above (the role's other embed defaults are `ollama`, 1024, `2s`, cache 256). `GET /v1/search?mode=semantic` then stops answering `X-AH-Degraded: semantic-unavailable`. The role refuses an address that is neither https nor a loopback, private or tailnet http address.
- **The worker's settings** (launchd plist `org.baditaflorin.agent-embed`, nothing in git): `--embedApi ollama --embedModel bge-m3 --dimensions 1024
  --batch 32 --maxChars 4000 --maxRetries 0` (wait for as long as it takes when the Mac sleeps) and `--textfile` for the metrics. GPU cost scales with
  characters, and the queue is mostly short with a long tail (500 queued events: median 96 characters, p90 4 KB, p99 33 KB), so embedding the first
  4000 characters costs 63 % of embedding 8000. Flash attention (`OLLAMA_FLASH_ATTENTION=1`) changed nothing for this model and is not set. A Mac
  that goes to sleep stops the worker and the questions alike; hold it awake for a large backfill (`caffeinate -i -s`, on AC power).
- **Measured on mac14 (M1 Pro, 2026-10-29).** bge-m3 is 1.2 GB, 100 % on the GPU, vectors of 1024 with unit length. Idle machine: 42 texts/s at 200
  characters, 16 at 1000, 4.6 at 4000 (batch 32); the real queue ran at 12 to 15 events/s (embed calls were 90 % of the worker's time). The first
  call after loading takes up to 100 s. A backlog of N events takes N/13 s: the 96,801 events of the first measurement need about 2 h, and the
  backlog grew to about 185,000 while the other three Macs back-filled their 30 days, so about 4 h. Search through the store costs 0.3 to 0.5 s
  (the question embedding is about 0.05 s of that).
- **Index recall (`hnsw.ef_search`).** The store leaves pgvector's default (40). With real vectors, 60 probes (the first nine words of an embedded
  reply, asked at limit 10) missed 4 results that the limit-200 answer ranked in its top 10 (93 % recall); `ef_search` 100 left 2 misses and 200
  left none, with no visible change in latency. It is set on the live database, not in git: `ALTER DATABASE agent_history SET hnsw.ef_search = 200`
  (new connections only: restart the store container to recycle its pool); undo with `ALTER DATABASE agent_history RESET hnsw.ef_search`.
- **Cold start.** After Ollama restarts the first question has to load the model (2 to 20 s) and times out at 2 s, so one or two searches answer
  `semantic-embedder-timeout` or `-failed` before it works. It heals itself; nothing is lost.
- **Check.** `agent_history_embed_backlog` (store metrics) falls to 0 while the worker runs; `agent-find --mode semantic "<a paraphrase of
  something said earlier>"` returns hits with no `X-AH-Degraded` header; with the Mac asleep or Ollama stopped a `hybrid` search still answers
  from text and exact, marked `semantic-embedder-timeout` or `semantic-embedder-failed`, and no search returns an error.
- **Roll back.** Remove the two variables from the host_vars file and re-run the play (the store goes back to `semantic-unavailable`); on the Mac
  `tailscale serve --tcp=8443 off`, `launchctl bootout gui/$(id -u)/org.baditaflorin.agent-embed`, `.../org.baditaflorin.ollama-query` and `.../org.baditaflorin.ollama`. Stored
  vectors stay in the database and cost about 8 KB each; they are not needed for any other search mode.
- **Rotate the embed token.** The store accepts one embed token: write the new value to OpenBao and the keychain, restart the agent container
  (or wait for the five-minute render), `SIGHUP` the store, then restart the worker. Between the two steps the worker's calls get 401 and it
  exits with status 3; launchd restarts it.

## Rotation

- Write token of one laptop: add a second line `host:new=token`, `SIGHUP` the store (`docker kill -s HUP agent-history-store`), switch the laptop, remove the old line in OpenBao, `SIGHUP` again. The OpenBao Agent re-renders within five minutes (`static_secret_render_interval`); restart the agent container to apply a change at once.
- Read token: remove one `name=token` line to revoke only that reader.
- Database password: needs a store restart and `ALTER ROLE`; plan it as a change.
- LUKS passphrase: `cryptsetup luksChangeKey` with the old and the new passphrase, then update OpenBao.

## Monitoring

The metrics bridge writes `agent_history.prom` into the node exporter's textfile directory every 60 seconds with the metrics-only token (`agent_history_scrape_success`, `agent_history_scrape_timestamp_seconds`, plus the store's own `agent_history_*`). The nightly canary scan (`agent_history_canary_scan_enabled`, off until the SQL file from agent-eval's `scripts/dbscan` is delivered) writes `agent_history_canary_*`. The alert rules are in a separate change (`config/prometheus/rules/agent-history.yml`). Nothing pages (owner decision of 2026-10-29, question 16): every alert is `warning` or `info`, including a canary leak; `warning` goes to the ntfy warning topic and `info` is dropped by Alertmanager.
The bridge assumes the Debian `prometheus-node-exporter` package (which the role installs if it is missing); whether the 0mcp Prometheus discovers this guest's exporter automatically (Scanopy file_sd) was not verified.

## Restore and rebuild

1. Rebuild (cheap): stop nothing on the laptops; re-run the collectors' backfill, which is idempotent. A 30-day backfill is about 15 to 30 minutes of store time.
2. Restore drill, once before widening and once at the pilot's end: restore the newest PBS snapshot of vm/155 into a throwaway vmid on an isolated bridge with the network disabled, unlock with the passphrase, start the project, check the event count, destroy the throwaway VM (`qm destroy <id> --purge`). A restored copy holds the transcripts: treat it as the production store.

## Whole-pilot rollback

Stop the collectors on all laptops; revoke the write and read tokens in OpenBao; remove the tailnet node and the grants (a removal is a human `apply` for the reconciler); `qm stop 155 --skiplock 1; qm destroy 155 --purge 1`; prune the PBS group `vm/155` and run garbage collection (space and data return after 40 to 48 hours); delete the OpenBao paths and the AppRole; remove the ssh alias; revert the declaration.

## What the pull request that added this runbook did not do

It changed git only. It did not provision the guest, touch the hypervisor, OpenBao, the tailnet, Prometheus or any laptop, pin or scan an image, or reload any rule. Merging it does not deploy.
