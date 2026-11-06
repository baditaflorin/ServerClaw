# Network policy as code: the allowed flows of the VMs of a hypervisor

Why this exists. On 2026-10-18 a published port of a VM was unreachable and the packets never arrived (a capture on the VM's network card showed
nothing). Three layers filter a VM, they were edited separately and by hand, and nothing said which one dropped the packet:

| Layer | Where | What it filters |
|---|---|---|
| `pve` | `/etc/pve/firewall/<vmid>.fw` on the hypervisor (`policy_in: DROP`) | everything arriving at the VM's network card, **outside the VM**: what it drops, the VM never sees |
| `input` | the guest's nftables, `table inet filter`, chain `input` | services listening on the VM itself |
| `forward` | the same table, chain `forward` | traffic that Docker rewrites to a container (published ports) |
| `docker_user` | the guest's iptables `DOCKER-USER` chain and the chains it jumps to | port-level limits in front of Docker's own rules (for example `KEYSTORE-LAN`, `config/keystore-mesh/lan-publish`) |

`config/network-policy/<host>.yaml` is now the one place that lists, per VM, which flows are allowed (source, protocol, ports), in which layers
each must exist, why, and who owns it. `scripts/netpolicy.py` reads the live state of all layers, compares it with the file, and answers "which
layer blocks this flow?". `snapshot`, `drift`, `check`, `why` and `render` never write to a host; `apply` is the only command that does, and only with
`--yes` (see [Applying a change](#applying-a-change-apply)). The first file, `0mcp.yaml`, was imported from the live state of the 0mcp hypervisor (18 VMs,
164 groups) and drifts from it by exactly nothing; every rule shape the hosts use is understood, and a rule the parser does not know is reported, not ignored
(this includes any guest rule that is not an `accept`: a `drop`, `reject`, `log` or `jump` is never filed as harmless).

## The file

```yaml
version: 1
host: 0mcp
collect: {ssh: hv-0mcp}                 # how the live state is read (an alias that reaches the hypervisor as root)
ipsets: {management: [...]}             # sets the Proxmox rules refer to (from cluster.fw)
inner_sources: [172.16.0.0/12, 192.168.0.0/16, 10.200.0.0/16, 100.64.0.0/10]   # Docker bridges and the tailnet: traffic that never crosses the VM's card as plain IP
lan_networks: [10.10.10.0/24]           # sources outside these and inner_sources are reported as stale
vms:
  '191':
    name: runtime-general-lv3
    pve:   {enable: '1', policy_in: DROP, policy_out: ACCEPT}
    guest: {nft: managed, input_policy: drop, forward_policy: drop}     # nft: absent for a VM without guest nftables
    groups:
      - from: [10.10.10.10, 10.10.10.30]       # one IPv4 address or CIDR per entry
        proto: tcp                              # tcp udp icmp vrrp any
        ports: ['18021']                        # a list, a range 'a-b', or '*'
        layers: [pve, docker_user]              # where the flow must exist
        purpose: keystore mesh node API for the 0docker failover chain
        owner: keystore
        decided: '2026-10-18'
```

Optional per group: `public: true` (open to `any` source on purpose), `wide_ok: <reason>` (a CIDR wider than /24), `iif: <interface>`, `unit: <dir>` (for a
`docker_user` group: the repo directory of the unit that puts the rules on the VM, named in `apply`'s plan); per VM: `exception: <reason>`
(no guest nftables on purpose), `notes: <text>`. Every group needs a `purpose`: the importer writes a placeholder (counted as `info`) until someone fills it in.

## Commands

```sh
python3 scripts/netpolicy.py check                                       # offline, what CI runs: valid, and no finding beyond the baseline
python3 scripts/netpolicy.py snapshot --host 0mcp --ssh hv-0mcp --out s.json   # read every VM of the hypervisor (read-only, about 40 s)
python3 scripts/netpolicy.py drift --policy config/network-policy/0mcp.yaml --snapshot s.json     # or --live
python3 scripts/netpolicy.py why --policy config/network-policy/0mcp.yaml --vm 191 --src 10.10.10.10 --port 18021 --live
python3 scripts/netpolicy.py render pve --policy config/network-policy/0mcp.yaml --vm 191        # what the file says the .fw should contain
python3 scripts/netpolicy.py import --snapshot s.json --out config/network-policy/0mcp.yaml      # re-baseline; keeps purposes and owners
python3 scripts/netpolicy.py apply --policy config/network-policy/0mcp.yaml --vm 191 --layers input,forward     # PLAN ONLY: what would change, nothing is touched
python3 scripts/netpolicy.py apply --policy config/network-policy/0mcp.yaml --vm 191 --layers pve --yes         # really apply, with auto-rollback
```

`why` is the debugging command: it prints, per layer, whether the flow is allowed by the policy and by the live host, then a verdict line, for example
(the control host that was blocked on 2026-10-18):

```
VM 191: 10.10.10.20 tcp/18021
  pve          policy: NOT allowed | live: NOT allowed          <- the layer that dropped it
  forward      policy: allowed by 10.10.10.20 any/*
  docker_user  policy: NOT allowed | live: NOT allowed
```

A layer only drops what it filters, and `why` says so instead of `NOT allowed`: `not filtered (the Proxmox firewall is off for this VM)`, `not filtered (no
guest nftables)`, `not filtered (chain policy accept)`, and for `docker_user` `not filtered (no DOCKER-USER rule for tcp/22)`: the DOCKER-USER chains jump
per port, so a port without a rule passes that layer. (Before 2026-10-21 every unmatched layer read `NOT allowed`, which was wrong for an unfiltered VM.)

Exit codes: `check` 0 ok / 1 a new finding; `drift` 0 in sync / 2 drift / 3 could not look (an unreachable hypervisor is never reported as "in sync").

## Changing a rule

1. Edit the VM's `groups` in `config/network-policy/<host>.yaml` (a purpose and an owner are part of the change) in a PR; CI runs `check` and the tests.
2. After the merge, put the change on the host with `apply` (below): it backs up, changes, verifies and rolls back by itself. Nothing applies a merged
   change automatically: until `apply` is run, `NetpolicyDrift` fires (1 h) and says which VM and layer differ.
3. `drift` must come back empty. If it does not, the host is not what the file says: fix whichever is wrong, do not leave it.

The `docker_user` layer (the `KEYSTORE-LAN`-style chains) is not applied by this tool: those chains belong to their own units, named by the group's
`unit:` (`config/keystore-mesh/lan-publish` on 0mcp VM 191, `config/0docker/docker-prod-lan-ports` on 0docker VM 101); change the unit and the policy
file together and let `drift` confirm. `apply` lists the `docker_user` flows that differ (`docker_user (by its unit) + ...`) and changes none of them.
This is also the layer for limiting a few Docker-published ports on a VM that is otherwise unfiltered: a DOCKER-USER jump per port restricts that
port only, where a Proxmox `policy_in: DROP` or a guest chain with `policy drop` would turn the whole VM to deny-all.

Never edit a `.fw` file only on the host: the next `drift` reports it, and the next person who rewrites the file from another source removes it
(this is how the 0mcp files went from 6 KB to 38 KB and back on their own, with only `.bak` files as history).

## Applying a change (`apply`)

`apply` makes one VM match its policy for the layers `pve` (the `.fw` file), `input` and `forward` (the guest's `table inet filter`). It always plans first;
without `--yes` it prints the plan and stops. The plan lists every rule line it would add or remove, and refuses (exit 1, nothing touched) when:

- a removal is in the plan and `--allow-remove` was not given (a stale or hand-added rule is only ever removed on purpose: a YAML PR that drops the group, then `apply --allow-remove`);
- the plan would change more than `--max-changes` lines (default 40), or the VM has live rules the tool does not model (it would edit blind);
- the change would cut the management path: `guard:` in the policy file lists flows that must stay open in every layer touched (`0mcp.yaml` guards `10.10.10.1 tcp/22`);
- the VM is not in both the policy file and the hypervisor, the guest agent does not answer, the VM has no `.fw` file or no guest nftables (enabling a firewall is
  not done by `apply`), or the guest has no readable `/etc/nftables.conf` with a `table inet filter` (the change could not survive a reboot).

A rule that carries several flows (a set of sources, a set of ports) of which only some are to go is **rewritten in place** with the ones that stay; the plan shows it as
`REPLACE <old rule>` / `with <new rule>  (same position)`, per layer, for the live table and for `/etc/nftables.conf` separately. The live rule changes through the same
atomic table load as every other change: it keeps its position among the rules, but the reload gives every rule of the table a new handle (unlike
`nft replace rule … handle <h>`, so do not script against old handles), the conf line is edited in its own layout (`/32`, comment and
indent kept) and never loaded, and in a `.fw` file only the `-source` or `-dport` list of that line changes. It goes through the same plan, `--allow-remove`, timer,
backups, verification and rollback as any removal. Refused, so it is split by hand: what stays is not one set of sources times one set of ports (one source loses one
of two ports another source keeps); a Proxmox macro cut to some of its protocols (`DNS` is tcp and udp); a source that comes from an ipset (other rules and VMs share
it). A guest rule with a named set, a mix of protocols, or a drop, log or jump is not modelled at all, so the whole VM is refused as before.

With `--yes` everything is read again from the live host (a plan from `--snapshot` is never applied: the state may have moved), then one script runs **on the
hypervisor** (over the alias in `collect.ssh`, as root) and does, in this order:

1. **arms the rollback first**: a transient `systemd-run --on-active` timer that restores every saved file and verifies the restore. If the ssh connection dies, the
   script crashes or the hypervisor loses the VM, the timer still fires (`--hold`, default 180 s). The timer is disarmed only after step 5;
2. checks the **sha of every file it will change** against the plan (somebody edited it since the plan: exit 1, nothing changed);
3. saves `fw.bak`, `nft_table.bak`, `nftables.conf.bak`, a self-contained `rollback.py` and `touched.json` under `/var/lib/netpolicy/apply/<UTC>-vm<id>/` (and
   `/etc/nftables.conf.bak-netpolicy-<UTC>` in the guest). `touched.json` is updated *before* each change, so a rollback restores exactly what was touched;
4. changes the layers: the `.fw` file and `pve-firewall compile`; the guest's live table through the guest agent as **one atomic `nft -f`**
   (`flush table inet filter` and the new table in the same transaction, so there is never a moment with an open or an empty chain); and `/etc/nftables.conf`
   (written, **never reloaded**, see below);
5. **verifies**: each layer re-read and equal to the intended flows, a TCP probe from the hypervisor to the VM on each `guard` port (22), and the
   guest agent still answering. Any failure, or a verification that reads nothing, rolls back and verifies the rollback itself.

| Exit code of `apply` | Meaning |
|---|---|
| 0 | applied and verified (or: nothing to change, or plan only) |
| 1 | refused by the plan, or a precondition failed on the host: **nothing was changed** |
| 5 | the change failed verification (or the connection was lost) and was **rolled back and the rollback verified** |
| 4 | rolled back but the restore could not be verified: read `/var/lib/netpolicy/apply/events.jsonl` and the run directory; the saved files are there |
| 3 | could not run (ssh, policy file): nothing was changed |

The run is logged as JSON lines in `/var/lib/netpolicy/apply/events.jsonl` and the rollback in `/var/lib/netpolicy/rollback.log` on the hypervisor.
`--simulate-failure verify` and `--simulate-failure crash` are the drills: they fail the verification, or die right after applying, and the rollback (inline or by
the real timer) must put every file back. Run both on staging VM 200 after any change to this code, never on a production VM.

### The reboot hazard: `/etc/nftables.conf` is persisted, never reloaded

What a guest loads at boot is `/etc/nftables.conf`, not the live table. `drift` compares both: `conf_flows_missing` is a rule that works now and **would be lost at
the next reboot**, `conf_flows_extra` is one that would come back. The conf files here are hand-written (2-space indent, `{ 22 }` sets, `/32`, trailing `# comments`),
and several start with `flush ruleset` (VM 121) or `destroy table inet filter` (VM 171): **reloading such a file with `nft -f` wipes Docker's NAT table and breaks every
published port.** So `apply` edits the conf text line by line in the file's own layout (the rest stays byte for byte) and never loads it; the live table is changed separately,
atomically, and only its own table. Do the same by hand if you ever must: edit the file, `nft -c -f` to check it, do not load it.

Both parsers strip a trailing `# comment` before reading a rule. (On 2026-10-19 they did not: 150 commented rules were treated as "not an allow", the conf looked 50 flows
short, and the first real `apply` added a duplicate of a rule that was already there. Fixed, with tests for both layouts; that duplicate was restored from its backup.)

## 0docker (onboarded 2026-10-21)

`config/network-policy/0docker.yaml` covers the three VMs of the 0docker hypervisor: VM 100 `ubuntu-24-04` (10.10.10.20), VM 101 `docker-prod`
(10.10.10.30) and VM 104 `debian-nginx-proxy-manager` (the edge, 10.10.10.10). It was imported from the live state and none of them filters
anything at any layer (the Proxmox firewall is off for all three and for the cluster, no guest has a `table inet filter`, `/etc/nftables.conf` is the
Debian default and `nftables.service` is disabled): the nine `pve-off` / `pve-policy` / `no-guest-nft` findings are in the baseline until decided.
The collector reads the VM address from `eth0`, so the addresses of VMs 100 and 104 (`ens18`) are recorded by hand; a re-import keeps them.

The one decision: VM 101's DomainScope ports (prod 23480-23483, staging 23580-23581) only from the edge, VM100, the hypervisor, the VM itself and
its Docker bridges, in `docker_user`, by the unit `config/0docker/docker-prod-lan-ports` (its README has the install, the checks and the rollback;
DomainScope audit finding 13, go-url-categorizer-api#2510). Every other port of VM 101 is open to the LAN as before.

`collect.ssh` is `root@10.10.10.1`: the drift job on CT108 reaches the hypervisor on the LAN with its own key (no alias needed). From the operator's
Mac pass `--ssh 0docker_bastion`, for example
`python3 scripts/netpolicy.py drift --policy config/network-policy/0docker.yaml --live --ssh 0docker_bastion`. The drift job picks the file up by
itself (`netpolicy-run` checks every `config/network-policy/*.yaml` at origin/main) and writes `netpolicy_0docker.prom`; the alerts are per
`hypervisor` label already.

## Findings

`check` reports what is wrong with the policy as written. A finding has a stable id; `config/network-policy/<host>.baseline.json` lists today's known ones,
CI fails only on a **new** one, and a fixed one must leave the baseline (a test enforces it).

| Class | Meaning |
|---|---|
| `pve-off`, `pve-policy` | the Proxmox firewall is not enabled for the VM, or its inbound policy is not DROP |
| `no-guest-nft` | the VM has no guest nftables: only the Proxmox layer filters it |
| `guest-input-policy`, `guest-forward-policy` | a guest chain whose default is not drop |
| `open-chain` | a guest chain that contains a bare `accept`: every packet passes and the rules after it never apply |
| `any-source` | a flow open to any source without `public: true` |
| `wide` | a source CIDR wider than /24 (Docker bridges and the tailnet are exempt: they never cross the VM's card) |
| `foreign-source` | rules for a source that is on no network of this host: usually left over from an old network layout |
| `shadowed` | a specific guest rule whose traffic the Proxmox firewall drops entirely, so it never fires |
| `dead-at-guest` | a flow the Proxmox firewall lets in and no guest chain accepts at all |
| `purpose` (info) | a group without a recorded purpose |

**What the first import of 0mcp found (2026-10-18), all in the baseline until decided:**

- VM 100 `hermes-agent` has **no filtering at any layer**: no Proxmox firewall, no guest nftables.
- The guest `forward` chains of VM 120 `docker-runtime-lv3` and VM 192 `runtime-control-lv3` contain a bare `accept` (on VM 120 at rule 73 of 228): forwarded
  traffic is unrestricted at that layer, and the Proxmox layer is the only limit.
- 16 stale sources on `10.10.10.0/24` (the 0docker LAN, not a network of this host) in the guest chains of VMs 121, 122, 171 and 180.
- VM 110 `nginx-lv3` and VM 171 `coolify-apps-lv3` accept a Prometheus scrape of port 9100 from the LAN in the guest, but the Proxmox firewall drops it first.
- VM 200 has no guest nftables; eight Proxmox rules (icmp and udp 41641 for the tailnet) on VMs 121 and 122 have no guest counterpart.
- Public ports are now marked `public: true` with a purpose: 80/443 on the standby edge, the realtime media ports on VMs 120/121 (by port numbers:
  owner to confirm) and the mail ports on VM 192 (owner to confirm).

## The drift job (CT108)

`netpolicy-drift.timer` on the builder CT108 runs `netpolicy-run` every 30 minutes. It fetches `config/network-policy/*.yaml` at `origin/main` (a merged,
reviewed change is the approval), runs the **installed** `netpolicy.py drift` for each file and writes the node-exporter textfile
`/var/lib/prometheus-node-exporter/textfile/netpolicy_<hypervisor>.prom` (the directory the builder's node exporter is started with). It only reads: as root through the alias in `collect.ssh` it runs `qm list`, `qm config` and,
through the guest agent, `nft list ruleset` and `iptables -S DOCKER-USER`. Exit codes of the run: 0 in sync, 2 drift (an alert, not a failed unit), 3 could not look.

```sh
scripts/netpolicy-install.sh            # install the files that are IDENTICAL to origin/main (merged code only), timer not enabled
scripts/netpolicy-install.sh --enable   # enable the timer and run it once
scripts/netpolicy-install.sh --status   # timer, last run, metrics files
```

Metrics: `netpolicy_vm_in_sync{hypervisor,vm}` (0 also when only the conf differs), `netpolicy_flows{hypervisor,vm,layer,kind=missing|extra}`,
`netpolicy_conf_flows{hypervisor,vm,chain,kind=missing|extra}` (the reboot hazard), `netpolicy_unparsed_lines{hypervisor,vm}`,
`netpolicy_could_not_look{hypervisor}` and the dead-man `netpolicy_last_run_timestamp_seconds{hypervisor}`. Alerts (`config/prometheus/rules/netpolicy.yml`,
unit tests in `tests/promtool/netpolicy_rules_test.yml`, shipped by the `monitoring_vm` role's adopted rule files):

| Alert | Fires when | Wait |
|---|---|---|
| `NetpolicyDrift` | a VM does not match its policy (a hand edit, or a merged change that was not applied) | 1 h |
| `NetpolicySilent` | the check has not run for 3 h | 10 min |
| `NetpolicyNotReporting` | the series is gone (`absent()`), the job was never installed or the textfile is not scraped | 3 h |
| `NetpolicyCannotLook` | the hypervisor, the guest agent or the git fetch could not be read for 2 h; an unreadable host is never "in sync" | 2 h |
| `NetpolicyUnmodelledRules` | live rules the tool does not understand: the policy is blind to them | 1 h |

Putting the rules on the monitoring VM by hand (what the role does on a converge): copy `netpolicy.yml` to `/etc/prometheus/rules/`, `promtool check rules`, reload Prometheus.

## Limits (on purpose, for now)

Only inbound accepts are modelled (the hosts have no `OUT` rules and no `DROP` rules; a guest rule that is a drop, reject, log or jump is reported as unmodelled,
`NetpolicyUnmodelledRules`, and makes `apply` refuse that VM). The hypervisor's own firewall (`cluster.fw` rules, `host.fw`) is not
modelled; its ipsets are read because VM rules refer to them. IPv6 is not modelled. The guest's other nftables tables (Docker, Tailscale) belong to those
tools and are not read. A port range is compared as written (`50000-58999` is one token, not 8,999 ports).
