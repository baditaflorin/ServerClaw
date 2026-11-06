# infer-pg-primary (VM701): direct Tailscale path and prepared DB client routes

2026-10-17. VM701 (`infer-pg-primary`, 10.70.10.10, tailnet 100.64.0.22) is the hot standby (backup copy) of the production `pg-primary`.
Nothing was promoted and no application DSN/DNS changed. This directory holds the hypervisor-side and VM-side pieces that make the tailnet path to it direct.

## The problem

Every tailnet peer reached VM701 through the DERP relay (Nuremberg): `select 1` from docker-prod (VM101) took 16-22 ms per round trip against ~0.4 ms on
the public path. The 0infer hypervisor's own tailscaled owns UDP 41641 on 203.0.113.20, so VM701's tailscaled (default port 41641) was masqueraded to a random
source port and no direct UDP path ever formed.

## The fix (same pattern as `infer-runtime-tailscale-direct.nft`, UDP 41642 for 10.70.10.30)

| Where | What | File |
|---|---|---|
| VM701 | `PORT="41643"` in `/etc/default/tailscaled`, restart tailscaled | `install-vm.sh` |
| 0infer hypervisor | nft table `ip infer_pg_ts_direct`: DNAT `eno1` UDP 41643 on 203.0.113.20 -> 10.70.10.10:41643 and SNAT back keeping the source port | `infer-pg-primary-tailscale-direct.nft` |
| 0infer hypervisor | one forward-accept rule in `infer_filter` (marked `pg-primary tailscale direct path`), live via `nft insert` and persisted in `infer-proxmox.nft` | `install-host.sh` |

Measured 2026-10-17: `tailscale ping` docker-prod -> VM701 `via 203.0.113.20:41643 in 1ms` (was `via DERP(nue) in 9-16ms`); `pgbench select 1` over the tailnet
15.7 ms -> 0.8-1.5 ms average (read-only, app DSN read in-process). The streaming replication does not use the tailnet (it runs over the public path
168.119.211.205) and was never interrupted.

Install / undo (the scripts back up what they change, validate with `nft -c`, load only their own table and never reload the whole ruleset):

```sh
tar -C config/0infer/pg-primary-tailscale-direct -cf - . | ssh 0infer_bastion 'd=$(mktemp -d) && tar -C $d -xf - && bash $d/install-host.sh [--undo]; rm -rf $d'
scp config/0infer/pg-primary-tailscale-direct/install-vm.sh 0infer_pg_primary:/tmp/ && ssh 0infer_pg_primary 'sudo bash /tmp/install-vm.sh [--undo]'
```

## Prepared client routes (policy in `config/tailscale/policy.hujson`, tests included)

| Client | Route | Grant | `pg_hba.conf` on VM701 |
|---|---|---|---|
| docker-prod VM101 (`domainscope_app`, `ansiblepguser`) | tailnet | 100.100.84.8 -> 100.64.0.22 tcp:5432 | hostssl, source 100.100.84.8 |
| dockerhost ubuntuvm1 (`ansiblepguser`, `global_addr_database`; no TLS, as on prod) | tailnet | 100.64.0.7 -> 100.64.0.22 tcp:5432 | `host global_addr_database ansiblepguser 100.64.0.7/32` + reject for the rest |
| SPIRE VM103 10.50.0.13 (`spire_prod`, `spire_0crawl`; not a tailnet node) | relay on the 0database hypervisor (retired with pve01 on 2026-10-22; the relay config is in git history) | 100.64.0.9 -> 100.64.0.22 tcp:5432 | hostssl `spire_prod`/`spire_0crawl`, source 100.64.0.9 |

`pg_hba.conf` on VM701 is not replicated from prod; the lines live in `/etc/postgresql/18/main/pg_hba.conf` (backups `pg_hba.conf.bak-<ts>` next to it).
Nothing in this directory moves traffic: every DSN still points at prod.
