# Tailscale Policy As Code, Metrics Grants And Exporter Listeners

The fleet's SaaS tailnet policy is now **managed as code**: `config/tailscale/policy.hujson` is the source of truth,
exported byte-for-byte from the live tailnet on 2026-10-12 (comments and ordering preserved), and
`scripts/tailscale_policy_sync.py` diffs, validates and applies it. The file holds real operator identities and tailnet
addresses, so it is private-repo only: `config/tailscale` is in `delete_paths` of
`config/publication-sanitization.yaml` and never reaches the public mirror. The sync tool and its tests use synthetic
fixtures only.

Nothing applies the policy automatically. Editing the file in git does not change the tailnet until an operator runs
`plan` then `apply` from CT108 (below). Between those two moments the file and the tailnet may differ, which is exactly
what the drift check reports.

## Files

| Path | Purpose |
|---|---|
| `config/tailscale/policy.hujson` | The policy: groups, tagOwners, grants, ssh, autoApprovers, nodeAttrs, tests. |
| `config/tailscale/lockout-guard.json` | SSH reachability the policy `tests` must keep proving (operator Mac to both bastions and pg-primary on :22). |
| `scripts/tailscale_policy_sync.py` | `check`, `export`, `plan`, `apply`, `drift` (python3 stdlib only). |
| `scripts/tailscale-policy-ct108.sh` | Runs the tool on CT108 from the operator's machine. |
| `tests/test_tailscale_policy_sync.py` | pytest unit tests on synthetic fixtures (`tests/fixtures/tailscale/`). |

## Change workflow

1. Edit `config/tailscale/policy.hujson` on a branch. Keep comments; add or adjust `tests` for every new grant.
2. `python3 scripts/tailscale_policy_sync.py check` locally (offline, no credentials). CI runs the same check plus the
   pytest suite on any PR touching `config/tailscale/**` (Woodpecker step `validate-tailscale-policy`).
3. Merge the PR.
4. From the operator machine, with the merged checkout:

   ```sh
   scripts/tailscale-policy-ct108.sh plan      # read-only: diff + POST /acl/validate + policy tests
   scripts/tailscale-policy-ct108.sh apply     # asks for confirmation; applies with If-Match
   scripts/tailscale-policy-ct108.sh plan --detailed-exitcode   # afterwards: no differences, exit 0
   ```

   The helper streams the tool and `config/tailscale/` into a throw-away directory on CT108 and runs it there
   (`ssh 0docker_bastion 'pct exec 108 -- ...'`); nothing is left behind except the plan and rollback state in
   `/var/lib/tailscale-policy-sync` (override with `TS_POLICY_STATE_DIR`).

What the commands do:

- `plan` reads the live policy (`GET /api/v2/tailnet/-/acl`, keeps the ETag), prints a semantic diff and a text diff,
  runs the offline checks, and calls `POST /acl/validate`, which also runs the policy `tests`. Any failure exits
  non-zero and records no plan. With `--detailed-exitcode` a plan with changes exits 2.
- `apply` refuses without a plan, with a plan older than 15 minutes, if the file changed since the plan, or if the live
  ETag or content changed since the plan (someone edited the tailnet in between). It saves the live policy as a rollback
  copy, then POSTs with `If-Match: <etag>` so Tailscale itself rejects a concurrent edit, and finally re-reads the live
  policy to confirm an empty diff. A plan is single-use.
- `check` is offline: HuJSON syntax; no allow-all (`"*"` to `"*"` or `"*:*"`); every `tag:` referenced anywhere exists in
  `tagOwners`; the lockout guard; the policy has `tests`.

### Credentials

None is stored in git or in CI. The tool fetches the OAuth client (`client_id`/`client_secret`, scopes `policy_file` and
`devices:core:read`) at run time from the vault secret `tailscale_policy_oauth_client` through
`/root/bin/fleet-vault.py raw`, the fleet-runner consumer path, run under the systemd-run credential wrapper documented
in that script. It exchanges it for a short-lived token and never prints the secret or token. This only works on CT108.
The tool prints only the ETag, hashes, diffs, and API error text.

### Rollback

`apply` prints the rollback path, `/var/lib/tailscale-policy-sync/rollback/policy.<utc>.<etag>.hujson` on CT108.
To roll back, pull that file, put it back at `config/tailscale/policy.hujson` (or point `--file` at it) and run `plan`
then `apply` again; or revert the git commit and re-apply, which is preferred because git stays the source of truth.
The rollback copy was the live, test-passing policy at apply time, so it passes `plan` unless the tailnet's devices or
tags changed since; `plan` shows the failing test if so.

## Drift detection

`python3 scripts/tailscale_policy_sync.py drift` (or `scripts/tailscale-policy-ct108.sh drift`) compares the live policy
with the file. Exit 0 = identical, 2 = drift, 3 = could not check. With `--textfile-dir` (default
`/var/lib/prometheus/node-exporter` on CT108) it writes `tailscale_policy.prom` for the node exporter's textfile
collector:

```
tailscale_policy_check_success 1
tailscale_policy_drift{kind="semantic"} 0   # rules/tags/groups/tests differ
tailscale_policy_drift{kind="text"} 0       # only comments or formatting differ
tailscale_policy_last_check_timestamp_seconds 1791788608
```

No scheduler is installed by this change. Running `drift` on a timer on CT108 (for example `systemd` timer every 15
minutes with `--textfile-dir`) and alerting on `tailscale_policy_drift == 1` or a stale
`tailscale_policy_last_check_timestamp_seconds` (older than one hour) is a follow-up that needs an operator decision
(it adds a unit on CT108). Until then run `drift` by hand, or rely on `plan` before every change.

## Lockout guard

The tailnet policy decides who can SSH to the bastions. `tests` are enforced by the API on every validate and apply, so
an edit that would cut the operator Mac off from the 0mcp and 0docker hypervisors or pg-primary on `:22` is rejected,
but only while those tests exist. `config/tailscale/lockout-guard.json` lists the pairs that must stay asserted as
`accept`; `check` (and so CI and `plan`) fails if a pair disappears. The pytest suite also pins the Mac-to-bastion pairs
inside the guard file, so weakening the guard shows up as a test failure, not only in review.

## Additive grants (2026-10-12)

| Source | Destination | Ports | Purpose |
|---|---|---|---|
| `tag:pve01-metrics`, pg-primary | own-pbs | tcp 8007 | Postgres backup path: vzdump and pgBackRest reach only the PBS API. |
| `tag:prometheus-monitoring` | 0docker VM100 (dockerhost), VM104 (nginx-proxy-manager), CT107 (pve-exporter, via hypervisor route), CT109 (scrapetheworld, via hypervisor route) | tcp 9100 | node_exporter scrape. |
| `tag:prometheus-monitoring` | 0own VM620 (own-pbs), VM630 (openobserve), VM640 (github-mirror), VM650 (pyroscope-canary, via hypervisor route) | tcp 9100 | node_exporter scrape. |
| `tag:prometheus-monitoring` | 0own build worker | tcp 9101 | Build worker and Woodpecker resource metrics exporter. |

Auto-approved advertised routes (single `/32` each, so a hypervisor cannot
advertise a wider range without console approval):

- `10.10.10.109/32` from the 0docker hypervisor (CT109).
- `10.60.10.50/32` from the 0own hypervisor (VM650).

New policy `tests` entries assert that the monitoring VM can reach every metrics
port above and cannot reach SSH (`:22`) or the PBS API on those hosts, and that
`tag:pve01-metrics` and pg-primary can reach `own-pbs:8007` but neither `:22`
nor `:443` there nor the 0own and 0mcp hypervisors. Re-run the policy tests
after any edit; the API rejects a policy whose tests fail.

## Exporter listeners and firewalls

These host changes were made by hand on 2026-10-12. They are now declared in
`inventory/fleet-observability.yml` and applied, only on request and one host at a time, by
`playbooks/fleet-observability.yml` (see `docs/runbooks/fleet-observability.md` for the safe way to run it, the live-vs-rendered
comparison and rollback).

| Host | Change | Managed by |
|---|---|---|
| 0mcp hypervisor | `prometheus-node-exporter` listens on the tailnet address at `:9100` and `:9102`. | `fleet_node_exporter` |
| 0docker hypervisor | systemd socket proxy `zdocker-hypervisor-metrics-proxy.{socket,service}` forwards its tailnet `:9100` to `10.10.10.1:9100` (the exporter cannot bind two addresses). | `fleet_node_exporter` |
| 0mcp hypervisor (build-metrics proxy) | systemd socket proxy `woodpecker-0exec-build-metrics-proxy.{socket,service}` (`FreeBind=true`) forwards its tailnet `:9103` to `10.10.10.30:9100` (docker-build VM exporter). Consumer: CT108 `100.114.37.21`, via the grant `tag:builder-metrics-controller -> 203.0.113.6/32 tcp:9103`. | `fleet_node_exporter` |
| 0docker hypervisor (stale `woodpecker-exec-proxy@9100.socket`) | kept stopped and disabled. | `fleet_node_exporter` (`state: disabled`) |
| 0docker VM100 | node_exporter on its tailnet address `:9100`. | `fleet_node_exporter` |
| 0docker CT108 | `tailscale serve --tcp=9100` to `10.10.10.108:9100` (userspace tailscaled). | `fleet_node_exporter` |
| 0own github-mirror (VM640) | `nftables`: only the monitoring VM's tailnet address may reach tcp 9100, on `tailscale0`. | `fleet_guest_firewall` |
| 0own VMs 620/630/640/650, 0docker VM104, CT107, CT109 | New `prometheus-node-exporter` installs with the textfile directory, bound to the tailnet or internal address. | `fleet_node_exporter` |
| 0docker and 0own hypervisors | Advertised `/32` routes `10.10.10.109/32` and `10.60.10.50/32`. | `fleet_tailscale_node` |
| 0mcp monitoring-lv3 (VM140) | CT108 `100.114.37.21` may read Prometheus `:9090` and Alertmanager `:9093` (GET only, consumers go-fleet-triage and the `fleet` MCP server, via tailscaled's userspace SOCKS5 on CT108). Three coupled pieces: the grant `100.114.37.21/32 -> 203.0.113.4/32 tcp:9090,9093`, an nftables allow rule for exactly that source (`network_policy.guests.monitoring`), and Alertmanager listening on `0.0.0.0:9093` (`alertmanager_runtime_listen_address`; Prometheus already listens on `0.0.0.0:9090`). Rollback: remove the nft rule, set the listen address back to `127.0.0.1:9093` and restart Alertmanager, drop `tcp:9093` from the grant. | `linux_guest_firewall`, `alertmanager_runtime`, policy sync |
| 0database hypervisor (pve01), pg-primary, own-pbs | PBS storage `own-pbs-0database`, job `pg-primary-daily-pbs` (02:30) with `/usr/local/sbin/vzdump-pg-metrics-hook`, pgBackRest prepared on pg-primary, PBS user/ACL/prune job. | `fleet_pg_backup` |

The `nginx` guest on the 0mcp fleet keeps its monitoring-only tcp 9100 firewall rule in
`inventory/host_vars/proxmox-host.yml` (`network_policy.guests.nginx`), rendered by `linux_guest_firewall`.

## Watch-outs found while verifying

- **Resolved 2026-10-12:** the 0mcp hypervisor's build-metrics proxy
  (`woodpecker-0exec-build-metrics-proxy.socket`, ws-0513 path) used to listen on
  the tailnet `:9100`, which node_exporter now owns. It moved to `:9103`, gets
  `FreeBind=true` (it died on 2026-10-11 when tailscaled restarted), and is
  modelled as managed. The grant for `tag:builder-metrics-controller` ->
  `203.0.113.6/32` `tcp:9103`, its policy test and the PVE `host.fw` line are in
  git and live. **Removed 2026-10-12 (user approved):** the older grant
  `tag:builder-metrics-controller -> 203.0.113.6/32 tcp:9100` and the cluster
  firewall rule for `100.114.37.21/32` tcp 9100. They reached the hypervisor
  exporter, not the builder VM; no consumer used them (CT108 reads via SSH
  tunnels and the `:9103` proxy; its only flow to `:9100` was an idle, zero-payload
  TCP connection).
- The 0mcp hypervisor's `:9102` listener is not covered by any monitoring grant
  (the monitoring VM cannot reach it today).
- Hypervisor node exporters (`203.0.113.5:9100`, `203.0.113.6:9100`) are
  now reachable from the monitoring VM and published by Scanopy under their
  legacy `pve_*_host_*` job names, so `PveHostNodeExporterUnavailable` no longer
  fires for them.
