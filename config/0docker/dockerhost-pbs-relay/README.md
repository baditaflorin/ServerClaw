# dockerhost-pbs-relay: VM 100 reaches own-pbs through the 0docker hypervisor

Installed on the 0docker **hypervisor** (`0docker_bastion`, 203.0.113.2, vmbr1 10.10.10.1, tailnet 100.64.0.5). The host is not managed by Ansible, so this directory is the source of truth.

## Why
The Docker host VM (VM 100, 10.10.10.20) backs itself up to own-pbs (100.64.0.11:8007, VM 620 on the 0own hypervisor) with `dockerhost-state-backup`. Its own tailscaled has **no direct path** to own-pbs: it sits
behind this hypervisor's NAT and shares the public address and the default 41641 port with this host's tailscaled, so Tailscale falls back to a DERP relay: measured 2026-10-21 about **2.8 MB/s** (22 Mbit/s, RTT 0.4 to
0.8 s under load). This hypervisor has a **direct** WireGuard path to own-pbs (`direct 203.0.113.14:20964`; both are Hetzner machines). So the VM talks to its hypervisor on the private bridge and the hypervisor
forwards the one TCP port over its own direct tailnet link:

    VM 100 -> 10.10.10.1:8007 (vmbr1) -> DNAT -> 100.64.0.11:8007 (tailscale0, masqueraded to 100.64.0.5)

Nothing about VM 100's own tailscaled changes (no restart, no port change), TLS still ends at own-pbs (the backup client pins the certificate fingerprint, so it does not care about the address), and the traffic
needs no new tailnet grant: `100.64.0.5 -> 100.64.0.11 tcp:8007` is the grant the hypervisor's own vzdump uses (config/tailscale/policy.hujson). VM 100's own grant stays as the fallback.

## What it is
* `dockerhost-pbs-relay.nft`: table `ip dockerhost_pbs_relay`, three rules, every one of them matching **source 10.10.10.20 only**: the DNAT (vmbr1 side only, destination 10.10.10.1, tcp 8007), the masquerade
  (out of tailscale0 to own-pbs tcp 8007 only) and an MSS clamp (tailscale0 has MTU 1280, VM 100 speaks 1500). Never reachable from the Internet (no enp5s0 match, nothing is published), no other VM can use it.
* `dockerhost-pbs-relay.service`: loads that one table at boot (this host's `/etc/nftables.conf` is a stock file and `nftables.service` is disabled; `fleet-lockdown` loads its own table the same way and does not flush the ruleset).
* `install-host.sh [--undo]`: validates with `nft -c`, installs `/etc/nftables/dockerhost-pbs-relay.nft` and the unit, enables and starts it, checks the rule is in the loaded table and undoes itself if not. `--undo` removes everything.

## Use
`dockerhost-state-backup` uses `backup-dockerhost@pbs!state@10.10.10.1:8007:own-pbs` as its repository (config.json). Fallback if the relay is ever down: the same string with `100.64.0.11` instead of `10.10.10.1`
(slow, but works through VM 100's own tailnet). Check from VM 100: `curl -sk -o /dev/null -w '%{http_code}\n' https://10.10.10.1:8007/` answers 200. Speed test from VM 100 (uploads random data, stores nothing):
`PBS_PASSWORD=$(cat /etc/dockerhost-state-backup/token.secret) PBS_FINGERPRINT=<fingerprint> proxmox-backup-client benchmark --repository backup-dockerhost@pbs!state@10.10.10.1:8007:own-pbs`.

## Install / undo
```
tar -C config/0docker/dockerhost-pbs-relay -cf - . | ssh 0docker_bastion 'd=$(mktemp -d) && tar -C $d -xf - && bash $d/install-host.sh; rm -rf $d'
tar -C config/0docker/dockerhost-pbs-relay -cf - . | ssh 0docker_bastion 'd=$(mktemp -d) && tar -C $d -xf - && bash $d/install-host.sh --undo; rm -rf $d'
```
Precedent: `config/0database/spire-vm701-relay` (the same idea on pve01 for SPIRE to the production Postgres; removed with pve01 on 2026-10-22, see git history).
