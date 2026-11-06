# Tailscale Policy As Code, Metrics Grants And Exporter Listeners

The fleet's SaaS tailnet policy is now **managed as code**: `config/tailscale/policy.hujson` is the source of truth,
exported byte-for-byte from the live tailnet on 2026-10-12 (comments and ordering preserved), and
`scripts/tailscale_policy_sync.py` diffs, validates and applies it. The file holds real operator identities and tailnet
addresses, so it is private-repo only: `config/tailscale` is in `delete_paths` of
`config/publication-sanitization.yaml` and never reaches the public mirror. The sync tool and its tests use synthetic
fixtures only.

By default nothing applies the policy automatically. Editing the file in git does not change the tailnet until an
operator runs `plan` then `apply` from CT108 (below). Between those two moments the file and the tailnet may differ,
which is exactly what the drift check reports. An optional, report-only-by-default reconciler on CT108 can apply the
narrow class of merged changes that are provably safe (see "Unattended reconciler" below); CI never holds the
credential and never applies.

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
  `tagOwners`; the lockout guard; the policy has `tests`; and the text is already in the form Tailscale stores it (below).
- `fmt` is offline: it rewrites the file in that stored form (whitespace only). `fmt --check` only reports.

### Tailscale's stored form

Tailscale keeps a posted policy re-formatted by `hujson.Format`: tab indentation; a list or object written on one line
stays on one line only while it fits in 80 columns (counted in bytes, from its opening bracket), otherwise one entry per
line with a trailing comma; consecutive one-line members of an object have their values aligned (`"src": ` / `"ip":  `).
The ETag of the live policy is the sha256 of that stored text (all 38 rollback copies on CT108 match their ETag,
2026-10-21). A file in any other form can never equal live byte for byte. `stored_form()` in the sync tool is a port of
that formatter, checked against hujson's own test table and against every live copy on CT108; CI fails a policy that is
not in that form (2026-10-20: #526's one-line nine-port lists made the reconciler re-apply on every run until #527
stored them as Tailscale does). Fix a red check with `python3 scripts/tailscale_policy_sync.py fmt` and commit the
result: it changes whitespace only.

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

## Unattended reconciler (additive-only, report-only by default)

`scripts/tailscale_policy_reconcile.py` runs on CT108 from `tailscale-policy-reconcile.timer` (every 15 minutes), next to
the vault credential. It is a pull reconciler: CI is not involved and never holds a credential. A merged, reviewed
change in git is the approval. Each run reads `config/tailscale/policy.hujson` at `origin/main`, compares it with the
live policy and decides:

| Decision | Meaning | Action |
|---|---|---|
| `in_sync` | identical, or live is exactly what Tailscale stores when git's text is posted | nothing |
| `text_only` | same rules, comments or ordering differ | applied (only with `--apply`), not counted against the daily cap, at most once per policy text |
| `additive` | only new `grants` and new `tests`, every new grant inside the guard and proven by a new test | applied (only with `--apply`) |
| `blocked` | anything else: a removal, a changed section (`groups`, `tagOwners`, `ssh`, `autoApprovers`, `nodeAttrs`), a failed offline check, a grant outside the guard | one alert, left for a human `plan` / `apply` |

**Guard for an auto-applied grant.** Only the keys `src`, `dst`, `ip`. At most 8 entries per side, each a single IPv4
host or an existing tag (no users, groups, autogroups, wildcards or CIDR ranges). `ip` is explicit `tcp:N`, `udp:N` or
`tcp:A-B` (at most 1000 ports) and never touches a management port (SSH, telnet, SMB, RDP, VNC, WinRM, hypervisor
APIs). Every `(src, dst, port)` must be accepted by a `tests` entry added in the same change, so Tailscale re-proves it
at apply time and a later edit that breaks it is rejected. At most 5 new grants per change. An existing test may change in one way only: destinations
move from its `deny` to its `accept` list, each opened (dst, port, protocol) by a grant added in the same change, and
nothing else about the test changes (#539: the canary agent's `:8082` was asserted closed until its grant). The test held
`deny` on live, the only rule change is the guarded new grants, and Tailscale runs every test before the apply, so the
`accept` passes only if a new grant opens it for that source, including a test that names the tagged node by address.
Any other change to a test is a removal and stays `blocked`.

**Before it applies** it requires the green CI status of that exact commit (`ci/woodpecker/push/woodpecker`),
re-validates with Tailscale (which runs every policy test), saves a rollback copy, applies with `If-Match: <etag>` and
re-reads the policy to confirm an empty diff. Bounds: one apply per run, at most 3 rule-changing (`additive`) applies per
24 hours, and a commit whose apply failed twice is not retried until `main` moves. A `text_only` apply changes no rule
(the semantic diff is empty before and is checked again after), so it is not counted and does not wait for the cap;
counting one spent the cap on 2026-10-20 and left #528 and #533 waiting until they were applied by hand. If such an apply
leaves live in a form neither git nor `stored_form()` predicts (Tailscale changed its formatter), the next `text_only`
run for the same text is `blocked` instead of applying again: adopt live's text (`scripts/tailscale-policy-ct108.sh
export`) and fix the formatter port. When the cap does hold a change, the notice says when the next slot frees.

**It cannot be talked into weakening itself.** The rules live in the INSTALLED copies of the reconciler, the sync tool
and `lockout-guard.json` under `/usr/local/lib/tailscale-policy-sync`. If any of them differs from git at the commit it
is judging, the run is `blocked` ("installed ... differs from git: review it, then reinstall"), so a PR that changes the
rules cannot also apply itself with the new rules. The installer only installs files identical to `origin/main`.

```sh
scripts/tailscale-policy-reconcile-install.sh            # install files and units
scripts/tailscale-policy-reconcile-install.sh --enable   # also enable the timer: REPORT ONLY, it never applies
scripts/tailscale-policy-reconcile-install.sh --status   # timer, last run, state, mode
```

**Status on CT108: APPLY IS ON since 2026-10-18 17:00 UTC** (the owner's decision: "if this gives it more autonomy then yes"; before that it was report-only and logged `would_apply` for days).
What that means in practice: a squash-merged change that is `text_only` or `additive` and inside the guard above is applied within 15 minutes after its commit's CI is green, with no person; everything
else (any removal, a grant touching a management port such as the hypervisor ssh/8006 mesh, an edit of groups/tagOwners/ssh/nodeAttrs) stays `blocked` and needs a human `plan`/`apply`.
Kill switch: `touch /var/lib/tailscale-policy-sync/reconcile/PAUSE` on CT108 (it keeps deciding and alerting, never applies); off for good: restore the empty `FLEET_TS_RECONCILE_ARGS=`
(the file `tailscale-reconcile.env.bak-pre-apply-20261018T1700Z` next to it is the report-only original). A git file that is not in the form Tailscale stores can no longer
merge (CI runs `check`), and if one does, live in its stored form counts as `in_sync` (metric `tailscale_policy_reconcile_git_stored_form 0`) instead of being re-applied every run.
The tier0-edge-grants job writes its policy through `stored_form()`.

Turning applying on is a deliberate edit, not an install side effect: set `export FLEET_TS_RECONCILE_ARGS=--apply` in
`/etc/fleet-runner/tailscale-reconcile.env` on CT108. Turn it off by removing that line, or pause it without a restart
with `touch /var/lib/tailscale-policy-sync/reconcile/PAUSE` (it keeps deciding and alerting, but never applies).

State and audit are in `/var/lib/tailscale-policy-sync/reconcile/` (`state.json`, append-only `events.jsonl`); rollback
copies are in `/var/lib/tailscale-policy-sync/rollback/` as for a manual `apply`. Metrics go to the node exporter textfile
`tailscale_policy_reconcile.prom`. One ntfy notice is sent per state change (waiting, blocked, applied, failed, back in
sync), never one per run and never with policy content or a secret. Notices, the failure circuit and the
daily cap follow the policy text, not the commit: an unrelated commit on `main` neither repeats a notice nor
resets a circuit, and a comment-only difference never pages. Exit codes: 0 ok or waiting, 1 an apply failed,
2 blocked (alert sent), 3 could not look.

Reading the journal (`journalctl -u tailscale-policy-reconcile.service`):

- A run held back by the daily cap says so on every run: `daily cap: 3 rule-changing applies in 24h; waits until about <UTC time>`, and
  writes a `deferred_cap` event (`waits_until` as the same text, `applied_in_window` as the count). The time is when enough of the
  applies in the window have aged out to bring the count under the cap. The one notice per state change carries the same time and the
  commit.
- `waits until about an unknown time` means the cap history (`applied` in `state.json`) holds something that cannot be read as a time
  (or a time too large to format), or is not a list. The reconciler fails closed: every unreadable entry counts as a spent slot. With
  three or more of them, or a field that is not a list, no rule-changing apply can happen (a text-only apply changes no rule and still
  goes through) until a human fixes the file: after reading the journal for how it got there, set `applied` to `[]`
  in `/var/lib/tailscale-policy-sync/reconcile/state.json` (or delete the field). With one or two unreadable entries the cap is lowered by
  that many until about 20 further applies push them out of the 20 entries kept. (An empty string or `{}` used to read as "no applies";
  they now hold the cap.)
- `reconcile: state.json field <name> had the wrong type (<type>) and was reset` means a field of `state.json` (not `applied`) had a shape
  the reconciler never writes, so it was dropped as if missing: counters restart from zero, a lost failure count resets the failure circuit (a policy
  that was failing is tried again, so a few more failed-apply notices can follow), a lost ETag takes a fresh baseline (a live change made at
  that moment goes unnoticed), a lost `unconverged` marker lets a text-only policy that was held for a human be applied once more, and a lost
  `notified` repeats one notice. A counter is wrong-typed also when it is negative or too large to be exported as a metric sample. The line
  names the type of the whole field (`dict` for a bad counter inside `failures` or `out_of_band`), and the value is never printed. The file
  itself is rewritten at the next timer run (`status` shows the line without saving anything).
- `reconcile: notice failed (<error class>[ HTTP <code>]): <title>` means the notifier raised: the channel refused the notice, could
  not be reached, or the configured value is not a URL. It never shows the URL (the topic is the secret) or the error text. Its absence is
  not proof of delivery: an ntfy-style server accepts a mistyped but well-formed topic and delivers to nobody, so check the topic once by
  sending a test. A failed notice is recorded as sent (it is not retried), so the line appears once per state change, not on every run.
- `reconcile: audit event not written (<error class>): <event>` means the audit line (`events.jsonl`) could not be appended after an
  apply or a deferral. The apply is still counted and saved; fix the log's permissions or the disk.
- An installed copy that differs from git blocks the run. Three files are compared with git at the head commit: this reconciler,
  `scripts/tailscale_policy_sync.py` and `config/tailscale/lockout-guard.json`. The comparison is byte for byte apart from line endings
  and trailing newlines, so even a comment-only edit counts. A failed read of one of the three from git blocks the same way: it is usually a
  transient network failure, and if the same error repeats the path no longer exists at that commit or the credential is broken (the
  journal line carries git's error; the installer cannot fix that). A file that is missing from CT108 does not reach this check: without
  the guard file the run stops before it can look (exit 3, `lockout guard file missing`, no notice, no metrics, so the dead-man alert is
  what tells you), and without the sync tool the run ends in a traceback (exit 1); the installer is the remedy for both. The installer
  installs those three plus the run wrapper and the two systemd units; the wrapper and the units are not compared.

After merging ANY change to `scripts/tailscale_policy_reconcile.py`, `scripts/tailscale_policy_sync.py` or
`config/tailscale/lockout-guard.json`, run `scripts/tailscale-policy-reconcile-install.sh` right after the merge, not later in the day. It
runs from a checkout at `origin/main` (it installs onto CT108 over the bastion; it cannot be run on CT108). From the next run (within 15
minutes) until a run has happened after the install, every run reports `blocked` (exit 2, `in_sync` 0 and `blocked` 1 in the metrics,
nothing applied, one "needs a human" notice that names the installer), even when the live policy equals git, and any additive grant merged
in the meantime waits. The plain install only copies files and reloads systemd, so the block ends at the first timer run after it (or at
once with `--enable`, which also starts a run). That run sends "back in sync" when live already equals git, or applies what was waiting
(an "applied" notice instead).

What is best-effort: the cap line, the `deferred_cap` event, the notice-failed line, the audit line written after an apply, and the last
"applied" line. They can never raise into the run, so a dead stdout/stderr or an unwritable `events.jsonl` cannot cost an apply its state
save, and a hand-edited `applied` field or a wrong-typed state field cannot crash the run. The verifying re-read after an apply is covered
too: whatever it raises, the apply is counted and saved and the run exits 1; the next run takes a fresh ETag baseline when the GET itself
failed, and starts from the ETag the GET returned when only its body did not parse. Known limits, not
changed by this: (1) a `state.json` that is not valid JSON, or not an object, is read as empty, so the cap count starts again from zero;
one that cannot be read at all (a directory, permissions) or is nested absurdly deep crashes every run until it is fixed; (2) a POST whose
answer is lost (a timeout or a reset while it is in flight) crashes the run before anything is saved: the apply may have landed, the next
run reads the new ETag as a change from outside, and the apply is not counted; (3) the other prints and audit lines of a run are not
guarded: a dead stdout from the start stops a run before anything is applied, a dead stderr stops a failed-apply report, and an unwritable
`events.jsonl` stops every path that logs before it saves its state except the apply itself: blocked, CI failed, report-only, could not
look (no `look_ok=0` metric), out-of-band detection (it recurs on every run) and a failed apply (the failure is not saved, so the failure
circuit never opens and a refused apply is retried on every run); (4) if stdout dies while the process exits the exit status can be 120
although the run finished; (5) the pending-apply gauge is the same for a cap hold as for a CI wait, so the journal and the `deferred_cap`
events are what tell them apart. These need a hand edit, a full disk, a broken pipe or a network failure at the wrong second.

What it does not do: it never removes or changes a rule, never edits SSH rules, groups, tag owners, auto-approved
routes or node attributes, and never applies a grant for a management port. Those stay a human `plan` / `apply`.

### Changes made outside the reconciler

Each run compares the live ETag with the one it last saw or produced itself. Any other ETag is a change it did not make:
it logs `out_of_band_change` (both ETags) in `events.jsonl`, sends one notice, and counts it in
`tailscale_policy_reconcile_out_of_band_changes_total{via=...}`. `via="sync_tool"` means `tailscale_policy_sync.py apply`
recorded the apply in `/var/lib/tailscale-policy-sync/applies.jsonl` (with its rollback copy); `via="unknown"` is the
admin console, another credential or an older copy of the sync tool, which recorded nothing. `FleetTailnetPolicyChangedOutsideReconciler`
(warning, `config/prometheus/rules/fleet-loops.yml`) fires on the next scrape and clears three hours later.

Both hand applies it was built for went through the sync tool on CT108 while the reconciler waited on its cap:
2026-10-20 15:32 UTC (six grants git did not have yet, which blocked the reconciler until #526 merged) and 2026-10-21
06:37 UTC (the merged #533; the next run was `in_sync` and nothing said a person had applied it). A merged additive
change never needs that. When the alert fires: read the two ETags in `events.jsonl`, run
`scripts/tailscale-policy-ct108.sh drift`, and adopt any live-only rule into git with a PR; a planned manual apply of a
`blocked` change needs nothing more. The sync tool's `apply` prints the same reminder before it asks for confirmation.

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

`drift` has no scheduler of its own. The reconciler below is the scheduled check: it compares live with git every 15
minutes and exports `tailscale_policy_reconcile_in_sync`, `..._blocked` and a dead-man timestamp, which an alert can
watch (`in_sync == 0` for more than an hour, or a stale `..._last_run_timestamp_seconds`).

## Lockout guard

The tailnet policy decides who can SSH to the bastions. `tests` are enforced by the API on every validate and apply, so
an edit that would cut the operator Mac off from the 0mcp and 0docker hypervisors or pg-primary on `:22` is rejected,
but only while those tests exist. `config/tailscale/lockout-guard.json` lists the pairs that must stay asserted as
`accept`; `check` (and so CI and `plan`) fails if a pair disappears. The pytest suite also pins the Mac-to-bastion pairs
inside the guard file, so weakening the guard shows up as a test failure, not only in review.

## Additive grants (2026-10-12)

| Source | Destination | Ports | Purpose |
|---|---|---|---|
| `tag:pve01-metrics`, pg-primary | own-pbs | tcp 8007 | **RETIRED (pve01 left the tailnet; #546 removed this grant and its tests, and `tests/test_standby_edge_grants.py` fails if the tag, the hypervisor or VM100 addresses come back).** It was the Postgres backup path: vzdump and pgBackRest reached only the PBS API. |
| `tag:prometheus-monitoring` | 0docker VM100 (dockerhost), VM104 (nginx-proxy-manager), CT107 (pve-exporter, via hypervisor route), CT109 (scrapetheworld, via hypervisor route) | tcp 9100 | node_exporter scrape. |
| `tag:prometheus-monitoring` | 0own VM620 (own-pbs), VM630 (openobserve), VM640 (github-mirror), VM650 (pyroscope-canary, via hypervisor route) | tcp 9100 | node_exporter scrape. |
| `tag:prometheus-monitoring` | 0own build worker | tcp 9101 | Build worker and Woodpecker resource metrics exporter. |

Auto-approved advertised routes (single `/32` each, so a hypervisor cannot
advertise a wider range without console approval):

- `10.10.10.109/32` from the 0docker hypervisor (CT109).
- `10.60.10.50/32` from the 0own hypervisor (VM650).

New policy `tests` entries assert that the monitoring VM can reach every metrics
port above and cannot reach SSH (`:22`) or the PBS API on those hosts, and that
`tag:pve01-metrics` and pg-primary could reach `own-pbs:8007` but neither `:22`
nor `:443` there nor the 0own and 0mcp hypervisors (retired with the grant above; those tests are gone). Re-run the policy tests
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
| 0mcp hypervisor (build-metrics proxy) | systemd socket proxy `woodpecker-0exec-build-metrics-proxy.{socket,service}` (`FreeBind=true`) forwards its tailnet `:9103` to `10.10.10.30:9100` (docker-build VM exporter). Consumer: CT108 `100.114.37.21`, via the grant `tag:builder-metrics-controller -> 100.64.0.6/32 tcp:9103`. | `fleet_node_exporter` |
| 0docker hypervisor (stale `woodpecker-exec-proxy@9100.socket`) | kept stopped and disabled. | `fleet_node_exporter` (`state: disabled`) |
| 0docker VM100 | node_exporter on its tailnet address `:9100`. | `fleet_node_exporter` |
| 0docker CT108 | `tailscale serve --tcp=9100` to `10.10.10.108:9100` (userspace tailscaled). | `fleet_node_exporter` |
| 0own github-mirror (VM640) | `nftables`: only the monitoring VM's tailnet address may reach tcp 9100, on `tailscale0`. | `fleet_guest_firewall` |
| 0own VMs 620/630/640/650, 0docker VM104, CT107, CT109 | New `prometheus-node-exporter` installs with the textfile directory, bound to the tailnet or internal address. | `fleet_node_exporter` |
| 0docker and 0own hypervisors | Advertised `/32` routes `10.10.10.109/32` and `10.60.10.50/32`. | `fleet_tailscale_node` |
| 0mcp monitoring-lv3 (VM140) | CT108 `100.114.37.21` may read Prometheus `:9090` and Alertmanager `:9093` (GET only, consumers go-fleet-triage and the `fleet` MCP server, via tailscaled's userspace SOCKS5 on CT108). Three coupled pieces: the grant `100.114.37.21/32 -> 100.64.0.4/32 tcp:9090,9093`, an nftables allow rule for exactly that source (`network_policy.guests.monitoring`), and Alertmanager listening on `0.0.0.0:9093` (`alertmanager_runtime_listen_address`; Prometheus already listens on `0.0.0.0:9090`). Rollback: remove the nft rule, set the listen address back to `127.0.0.1:9093` and restart Alertmanager, drop `tcp:9093` from the grant. | `linux_guest_firewall`, `alertmanager_runtime`, policy sync |
| 0database hypervisor (pve01), pg-primary, own-pbs | **RETIRED: pve01 was cancelled (its VMs stopped 2026-10-21), so what ran on its hypervisor and on pg-primary VM100 is gone.** Historical record of the 2026-10-12 setup: PBS storage `own-pbs-0database`, job `pg-primary-daily-pbs` (02:30) with `/usr/local/sbin/vzdump-pg-metrics-hook`, pgBackRest prepared on pg-primary, PBS user/ACL/prune job. | `fleet_pg_backup` |

The `nginx` guest on the 0mcp fleet keeps its monitoring-only tcp 9100 firewall rule in
`inventory/host_vars/proxmox-host.yml` (`network_policy.guests.nginx`), rendered by `linux_guest_firewall`.

## Watch-outs found while verifying

- **Resolved 2026-10-12:** the 0mcp hypervisor's build-metrics proxy
  (`woodpecker-0exec-build-metrics-proxy.socket`, ws-0513 path) used to listen on
  the tailnet `:9100`, which node_exporter now owns. It moved to `:9103`, gets
  `FreeBind=true` (it died on 2026-10-11 when tailscaled restarted), and is
  modelled as managed. The grant for `tag:builder-metrics-controller` ->
  `100.64.0.6/32` `tcp:9103`, its policy test and the PVE `host.fw` line are in
  git and live. **Removed 2026-10-12 (user approved):** the older grant
  `tag:builder-metrics-controller -> 100.64.0.6/32 tcp:9100` and the cluster
  firewall rule for `100.114.37.21/32` tcp 9100. They reached the hypervisor
  exporter, not the builder VM; no consumer used them (CT108 reads via SSH
  tunnels and the `:9103` proxy; its only flow to `:9100` was an idle, zero-payload
  TCP connection).
- The 0mcp hypervisor's `:9102` listener is not covered by any monitoring grant
  (the monitoring VM cannot reach it today).
- Hypervisor node exporters (`100.64.0.5:9100`, `100.64.0.6:9100`) are
  now reachable from the monitoring VM and published by Scanopy under their
  legacy `pve_*_host_*` job names, so `PveHostNodeExporterUnavailable` no longer
  fires for them.
