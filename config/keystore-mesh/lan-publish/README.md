# Keystore mesh node: API on the LAN, for the failover chain only

2026-10-18, decided by the owner: the 0docker failover chain verifies keys against a keystore **mesh node** instead of restoring an hourly keystore
snapshot (the snapshot can be an hour old, so a key revoked after it is accepted again, and keys it issues during an outage are lost; a mesh node
is current within seconds). The 0mcp mesh node (`runtime-general-lv3`, VM 191, LAN `10.10.10.91`) published its API (`/verify`, `/issue`) on
`127.0.0.1:18021` only. This publishes it on the LAN address as well and lets **only the listed hosts** reach it.

| Host | Why |
|---|---|
| `10.10.10.10` nginx-lv3 (VM 110) | the standby edge's `auth_request` upstream |
| `10.10.10.30` docker-build | the promoted vault |

Anything else on the LAN is dropped. `/issue` stays protected by the admin token, which the chain does not hold: the failover check uses a pre-issued
read-only test key, never an admin token.

## Parts

- compose: one more port mapping on the node, `"${API_LAN_PUBLISH:-127.0.0.1:18022}:${PORT:-8080}"`, and `API_LAN_PUBLISH=10.10.10.91:18021` in the node's
  `.env` (the default maps a harmless loopback port, so a node that does not set it exposes nothing new). The loopback mapping `127.0.0.1:18021` stays.
- `keystore-lan-firewall` + `keystore-lan-firewall.service`: a chain `KEYSTORE-LAN` jumped to from `DOCKER-USER` for traffic that arrived on `eth0` for
  `10.10.10.91:18021` (matched on the original destination, because Docker has already rewritten it). The chain is replaced in one
  `iptables-restore --noflush` transaction, so there is never a moment with an empty (open) chain. The unit re-applies it after `docker.service` starts.
- `/etc/keystore-lan-allow.conf`: the allowed hosts, **one IPv4 address per line, no ranges, no wildcards** (a bad line stops the run and leaves the
  rules as they were). To add a host: add its address, `sudo systemctl restart keystore-lan-firewall`.

## Proxmox firewall: the layer outside the VM (applied 2026-10-18)

VM 191 has its own Proxmox firewall (`/etc/pve/firewall/191.fw` on `operator-bastion`, `policy_in: DROP`, one explicit rule per source and port). A port that
the VM publishes is invisible to the LAN until that file allows it, and the packets never reach the VM (a capture on its `eth0` shows nothing). Two rules
were added after the existing `-dport 22` line, exactly the two hosts and the one port:

```
IN ACCEPT -source 10.10.10.10/32 -p tcp -dport 18021 # keystore mesh node API: standby edge nginx-lv3 (0docker failover chain)
IN ACCEPT -source 10.10.10.30/32 -p tcp -dport 18021 # keystore mesh node API: docker-build, promoted vault (0docker failover chain)
```

Backup of the file before the change: `/etc/pve/firewall/191.fw.bak-keystore-lan-20261018T174836Z`; `pve-firewall compile` was clean and the daemon picked the rules
up within seconds. To add a host: the same line with its address in `191.fw`, **and** its address in `/etc/keystore-lan-allow.conf` on the VM + `systemctl
restart keystore-lan-firewall` (the guest `nftables` forward chain already accepts the LAN hosts, so the DOCKER-USER chain here is the port-level control).
Rollback of this layer: delete the two lines (or restore the backup). There is no other source of truth for these per-VM rules in the repo.

## Install

```sh
scp -r config/keystore-mesh/lan-publish 0mcp_lv3_runtime:/tmp/ && ssh 0mcp_lv3_runtime 'sudo bash /tmp/lan-publish/install-vm.sh'   # also: --check, --undo
```

Then the compose line and `.env` entry above, and `docker compose up -d` (a few seconds of restart of this node's keystore container; the mesh's other
nodes cover it). Verify from an allowed host: `curl -s http://10.10.10.91:18021/version`; from any other LAN host the connection must time out.

## Rollback

`sudo bash install-vm.sh --undo` removes the rules and the unit; take the `API_LAN_PUBLISH` line out of `.env` and `docker compose up -d`. The node
backups made at install time are in `/opt/services/go_apikey_service/lan-publish-<time>/`.

## Known limits

- At boot, Docker may start the container a moment before the unit applies the rules (seconds). The API is key-authenticated and `/issue` needs the
  admin token, so the window is small, but it is not zero.
- The node is one replica: a key whose home is the (dead) 0docker writer, such as a single-use key, answers 503 "try again" and is never granted twice;
  new keys can only be issued on a writer node (see the promotion of the 0infer node).
