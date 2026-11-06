# DomainScope ports on VM101 docker-prod: only the edge and the known callers

Finding 13 of the 2026-10-19 DomainScope security audit (baditaflorin/go-url-categorizer-api#2510): DomainScope prod runs on VM101
`docker-prod` (10.10.10.30) on the 0docker hypervisor, which filters nothing at any layer (no Proxmox VM firewall, no guest nftables,
an empty `DOCKER-USER`). Any host on 10.10.10.0/24 could call the published ports directly and skip the edge nginx's admin gate, its
`/metrics` ACL and its rate limits. This limits **only the six DomainScope ports**; every other port and flow of the VM stays as it was.

The decision lives in `config/network-policy/0docker.yaml` (VM 101, layer `docker_user`); `domainscope-lan-allow.conf` here carries the
same sources and ports for the unit on the VM, and `tests/test_netpolicy.py` fails if the two differ. `netpolicy.py drift` compares the
live `DOCKER-USER` chain with the file every 30 minutes (`NetpolicyDrift`).

| Port | What | Allowed callers (measured 2026-10-21, go-url-categorizer-api#2638) |
|---|---|---|
| 23480 | prod web | edge VM104 `10.10.10.10` |
| 23481 | prod api | edge; VM100 `10.10.10.20` (POST /api/v1/categorize ~1,600/day, Prometheus `/metrics` every 30 s); hypervisor `10.10.10.1` (GET /health) |
| 23482 | prod api-next (backup upstream during a start-first deploy, published only then) | edge |
| 23483 | prod frontend-next (the web backup upstream during a start-first deploy, published only then) | edge |
| 23580 | staging web | edge |
| 23581 | staging api | edge; VM100 (staging `/metrics` scrape) |

The allow list is one list for all six ports: `10.10.10.1`, `10.10.10.10`, `10.10.10.20`, `10.10.10.30` and `172.20.0.0/14`. No tailnet
caller was seen.

## How it filters

- **IPv4**: the chain `DOMAINSCOPE-LAN` (`-s <source> -j RETURN` per allowed source, then `DROP`) is jumped to from `DOCKER-USER` once per
  port, for packets that arrived on `eth0` in the original direction of a connection to that port (`-m conntrack --ctorigdstport N --ctdir
  ORIGINAL`: the port before Docker rewrote it). This is the forward path the published ports take; Docker's NAT and its own chains are
  never touched, so publishing keeps working.
- **IPv6**: docker-proxy also listens on `[::]` for these ports, and the link-local address of `eth0` reached it (a GET /health from the
  hypervisor over `fe80::...%vmbr1` answered 200 on 2026-10-21). That path is INPUT, not DOCKER-USER, and the policy tool does not model
  IPv6, so the unit also adds `DOMAINSCOPE-LAN6` (`DROP`) jumped to from `ip6tables INPUT` for the same ports on `eth0`.
- What is **not** filtered, on purpose: traffic that does not arrive on `eth0`. Deploy probes on `127.0.0.1` (docker-proxy), the VM calling
  its own `10.10.10.30` (Docker's OUTPUT DNAT) and containers calling a published port from a Docker bridge never cross `eth0`, so the
  `10.10.10.30` and `172.20.0.0/14` entries are defence in depth, not the path those calls take. Tailnet traffic (`tailscale0`) is accepted by
  Tailscale's `ts-forward` chain before `DOCKER-USER` and is governed by the tailnet policy.
- Each chain is replaced in one `iptables-restore --noflush` transaction, and a jump is added only after its chain is filled: there is never a
  moment with an empty chain in place. The unit re-applies after `docker.service` starts (Docker keeps `DOCKER-USER` as it is).

## Install (after the merge)

From the operator's Mac (`0docker_docker_prod` is root@10.10.10.30 through the 0docker bastion; from CT108 it is `root@10.10.10.30`):

```sh
tar -C config/0docker -cf - docker-prod-lan-ports | ssh 0docker_docker_prod 'rm -rf /root/docker-prod-lan-ports && tar -x -C /root && bash /root/docker-prod-lan-ports/install-vm.sh --hold 300'
```

`install-vm.sh` validates the conf, backs up the filter tables and the files to `/var/lib/domainscope-lan-firewall/<UTC>/`, **arms an automatic
undo** (`systemd-run --on-active=300`), installs and starts the unit, and checks that the live rules are exactly the conf's. A failed check undoes
at once (exit 5). Then, within the hold time:

```sh
ssh 0docker_nginx 'curl -sS -o /dev/null -w "%{http_code}\n" --max-time 5 http://10.10.10.30:23481/health'     # 200 (edge)
ssh 0docker_docker 'curl -sS -o /dev/null -w "%{http_code}\n" --max-time 5 http://10.10.10.30:23481/metrics'   # 200 (VM100, Prometheus)
ssh 0docker_bastion 'curl -sS -o /dev/null -w "%{http_code}\n" --max-time 5 http://10.10.10.30:23481/health'   # 200 (hypervisor)
ssh 0docker_builder 'curl -sS -o /dev/null --max-time 5 http://10.10.10.30:23481/health; echo "exit $?"'          # exit 28: CT108 is not allowed
ssh 0docker_bastion 'curl -sS -g -o /dev/null --max-time 5 "http://[fe80::be24:11ff:fe75:123e%vmbr1]:23481/health"; echo "exit $?"'  # exit 28: IPv6 closed
curl -sS -o /dev/null -w "%{http_code}\n" https://<public DomainScope host>/health                            # 200 through the edge
python3 scripts/netpolicy.py drift --policy config/network-policy/0docker.yaml --live                              # 0 drifted
ssh 0docker_docker_prod 'bash /root/docker-prod-lan-ports/install-vm.sh --confirm'                                 # keep it
```

If any check fails, do nothing: the undo fires by itself at the end of the hold. Status: `install-vm.sh --check`.

## Rollback

```sh
ssh 0docker_docker_prod 'bash /root/docker-prod-lan-ports/install-vm.sh --undo'
# or, without the files: /usr/local/sbin/domainscope-lan-firewall --remove && systemctl disable domainscope-lan-firewall
```

Then revert the VM 101 group in `config/network-policy/0docker.yaml` (otherwise `NetpolicyDrift` fires after an hour).

## Changing the list

Edit `domainscope-lan-allow.conf` **and** the VM 101 group in `config/network-policy/0docker.yaml` in one PR (the test keeps them equal), merge,
then run the install again: it replaces the chain in one transaction and removes the jumps of ports that left the conf.

## Known limits

- At boot, Docker may start the containers a few seconds before the unit applies the rules (the same window as the keystore LAN unit).
- The policy tool sees the IPv4 rules only (`DOCKER-USER` and the chain it jumps to); the IPv6 chain is checked by `install-vm.sh --check`.
