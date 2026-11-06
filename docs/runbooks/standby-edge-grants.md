# Standby edge: tailnet grants for the pool backends

The standby gateway (the 0mcp edge VM110, tailnet node `edge-standby-0mcp`, 100.84.241.55) keeps every production pool's surviving servers, and those are tailnet addresses (the infer runtime
100.64.0.24 and three more pool runtimes). Its outbound access is granted by exact port in `config/tailscale/policy.hujson`. A pool whose port is not granted loads fine in `nginx -t` and answers
**504** through the standby gateway: invisible until the daily rehearsal's all-names probe (fleet-state `scripts/tier0/standby-probe.sh`, `PROBE_ALL ... failing=N` in the rehearsal log) counts it.

**2026-10-18:** 92 of 374 pool-served names failed 504. A TCP connect from the edge to every production pool backend ip:port reached 190 of 293; all 103 failures are listening on their hosts
(89 infer runtime, 5 runtime-general-lv3, 4 the 0own runtime, 5 the 0database runtime), i.e. missing grants, not stale pool servers. The grants were generated from that measurement
(`scripts/standby_edge_grants.py`) and applied through the repo's path; the measurement is kept as `tests/fixtures/standby_edge_reach_2026-10-18.txt` and a test pins that the policy grants exactly those ports.

## When the probe fails again (new pools added since)
1. Measure from the edge, on the ports the production gateway's pools use now: list the non-primary `upstream` servers of the gateway (names and ports only), then from VM110
   `timeout 3 bash -c "exec 3<>/dev/tcp/$ip/$port"` for each pair (`OPEN|CLOSED ip port` lines, 24 in parallel takes seconds).
2. Separate missing grants from stale servers: a CLOSED port that is listening on its host (`ss -ltn` there) is a missing grant; one nothing listens on is a stale pool server (fix the pool, not the grant).
3. `scripts/standby_edge_grants.py --reach reach.txt --verify` prints the grants and tests (one `/32` destination per host, explicit ports, a range only over ports that are all needed; `--verify` runs the
   unattended reconciler's own guard on them). Paste them into `grants` / `tests` of the policy, `scripts/tailscale-policy-ct108.sh plan` (it validates and runs every policy test against Tailscale), PR.
4. After the squash-merge the reconciler on CT108 (`tailscale-policy-reconcile.timer`, every 15 minutes) applies an additive change that passes its guard and has green CI. If `drift` shows a live-only
   entry the reconciler is BLOCKED (it was from about 2026-10-14 to 2026-10-18 because of one documented live-only grant) and nothing is applied: adopt the live text (`scripts/tailscale-policy-ct108.sh export`) into git first.
5. Verify with the next rehearsal (`PROBE_ALL failing=` falls) or by hand: `sudo tier0-run tier0-gateway-promote.sh --rehearse` on infer-tier0.

## Automation: the loop closes itself (2026-10-18, hardened 2026-10-19 after an independent review)
Nobody has to notice any more. Four pieces, all reviewed code in git:
1. **Measure (runner, hourly :50).** fleet-state `tier0-edge-compat.sh` TCP-tests every tailnet backend of the standby pools from the edge VM and lists the closed pairs in its result; **only an answer for a pair the runner
   asked about counts, once** (the edge is the less trusted vantage point: a compromised edge cannot nominate ports of its own; the rest is counted as `ignored N answer(s)` in the log). The wrapper `tier0-edge-compat`
   exports `tier0_runner_edge_backend_closed_streak{backend_ip,backend_port}` = how many hourly runs in a row the pair has been closed (a missing grant stays closed, a tailnet hiccup does not).
2. **Decide and propose (CT108, hourly :20).** `/usr/local/bin/tier0-edge-grants.sh` takes a sparse, shallow, blob-less clone of this repo (the policy and five other files: a few MB, not the whole tree) and runs the **installed**
   job `/usr/local/lib/tier0-edge-grants/standby_edge_grants_job.py` against it. The job:
   - first checks that every installed file it uses equals main (below) and that `gh` can read CI (`pr checks --json`), the token may push, and so may git (a `push --dry-run` creates nothing): a broken PR path is found hours
     before the first grant needs it, not by the first grant;
   - reads the pairs closed for **2 runs** from the primary Prometheus, only from the runner's own series (`job="tier0_node_exporter",role="tier0"`: no other scraped target can speak for it) and only while the check
     itself is ok, fresh (a negative age, NaN or +Inf is not fresh) and plain numbers; keeps those on a pool runtime (the four hosts in `DESTINATIONS`), in the pool port ranges (3000-3999, 8000-8999, 18000-18999), not on
     the never list (keystore API/mesh, vault, proxies, databases, exporters) and not a management port (the reconciler's own list: 3389 sits inside 3000-3999), not already granted explicitly, and **listening** on the
     destination (`ss` over ssh from CT108: a stale pool server is not a grant). More than **40 new ports in one run** changes nothing (an edge whose tailnet is down shows everything closed) and raises
     `Tier0EdgeGrantsNeedHuman`;
   - judges everything against the **LIVE** policy (the one the reconciler compares with, read through the same Tailscale credential path): **main must already equal it** (otherwise the job waits: it never stacks a change on
     one the reconciler has not applied, which made 3 foreign + 3 own = 6 grants, over the reconciler's limit of 5, and it never runs while the reconciler is paused), then the reconciler's own `classify()` of live to main+additions must
     say `additive`, its guard and the offline check must pass, Tailscale must validate it (every policy test), and the difference must be **exactly the job's own grants and tests**, not one more, not one less;
   - APPENDS new grants (one per host, /32, exact ports) and their tests above the two `standby-edge-auto-grants ... END` markers in `config/tailscale/policy.hujson` (additions only: a modified grant is a removal plus an
     addition, which the reconciler blocks), commits **that file and nothing else** (the staged list is checked), opens a PR (`tier0-edge-grants-<time>`), waits (up to 25 minutes) until **both** Woodpecker contexts
     `ci/woodpecker/pr/woodpecker` and `ci/woodpecker/push/woodpecker` have reported and passed (an unrelated fast check or a skipped one is not CI), looks at both kill switches again, and squash-merges.
     **Whatever stops it once the PR exists** (red or silent CI, a refused merge, a kill switch, systemd's SIGTERM at the 40-minute timeout) **closes the PR and deletes the branch**;
   - what keeps a broken day from becoming a flood: every ATTEMPT (not only a merge) is written to `state.json` **before** the PR flow starts; at most **2 attempts a day** (the reconciler applies 3 a day, one stays free for a
     person's change), 2 hours apart, and after a failed attempt the wait triples (6 h, 18 h, then a day) while `ok` stays 0, so `Tier0EdgeGrantsFailed` fires instead of a PR an hour. An open automatic PR older than 2 hours
     (a run that died) is closed by the next run and counts as a failure; a younger one is waited for.
3. **Apply (CT108, every 15 minutes).** The tailnet policy reconciler (apply on) applies the merged additive change after the push pipeline of that commit is green.
4. **Confirm.** The next edge-compat runs show the ports open; `Tier0EdgeBackendPortsClosed` (5 h) only fires if this chain did not do it. From the first sight of a missing grant to open ports: about 2 hours.
Metrics `tier0_edge_grants_*` (textfile on CT108) and alerts `Tier0EdgeGrantsFailed` / `Stale` / `Missing` / `NeedHuman` / `PrStuck` / `InstalledDrift` (rules in `config/prometheus/rules/tier0.yml`).

**What runs is what was reviewed.** The job executes only INSTALLED copies: itself and `standby_edge_grants.py` in `/usr/local/lib/tier0-edge-grants/`, and the reconciler's own `tailscale_policy_sync.py`, `tailscale_policy_reconcile.py`
and `lockout-guard.json` in `/usr/local/lib/tailscale-policy-sync/` (the tools that fetch the policy credential and judge changes). Before it loads or runs anything it compares every one of them with main (line endings aside) and
**runs nothing if one differs** (`installed_matches_git` 0, exit 3, `Tier0EdgeGrantsInstalledDrift` after 3 h): a merge to `scripts/` never executes by itself with the policy credential. (Before 2026-10-19 the wrapper cloned main and ran the
job from the clone, so any merge touching `scripts/` ran as root within the hour.)

**Install on CT108 (from an up-to-date main, like the reconciler):** `scripts/tier0-edge-grants-install.sh` (refuses anything that is not identical to `origin/main`; compiles first; keeps what it replaces in
`/root/tier0-script-backups/tier0-edge-grants-<time>/`; never touches `PAUSE`, the state or the timer), then `systemctl enable --now tier0-edge-grants.timer` the first time. `scripts/tier0-edge-grants-install.sh --check` compares
everything the job runs with main and exits 1 when the job would refuse. The reconciler's tools are installed by `scripts/tailscale-policy-reconcile-install.sh`; after a change to either, run both installers.
Look at what it would do any time with `tier0-edge-grants.sh --dry-run` (prints `RESULT_JSON` with the pairs it would add and every pair it rejected, found stale, could not verify or found already granted; reads the live policy through Tailscale,
touches neither GitHub nor the state nor the metrics).
**Kill switches:** `touch /var/lib/tier0-edge-grants/PAUSE` (the job keeps reporting, never opens a PR; one that is open when it appears is closed unmerged) and the reconciler's own `<state-dir>/reconcile/PAUSE` (the job waits too).
State: `/var/lib/tier0-edge-grants/state.json` (a file that is not what the job wrote counts as absent). **Rehearse a change of the job** with `tier0-edge-grants.sh --rehearse --inject FILE`: the whole PR flow for real (branch, PR, both CI
contexts) but the PR is closed instead of merged, no state, no metrics, and it ignores PAUSE (you asked for it).

**When it refuses or waits** (read the `RESULT_JSON` line in `journalctl -u tier0-edge-grants.service`):
- `waiting: main and the live tailnet policy differ` (ok stays 1, `tier0_edge_grants_waiting_reconciler` 1): something merged is not applied yet (normal for ~30 minutes after a merge), or the reconciler is blocked/paused
  (`scripts/tailscale-policy-ct108.sh drift` shows it; its own alerts `fleet-loops.yml` say so); a live-only entry (the 2026-10-18 pg-primary replication grant was one) is adopted into git by PR (the union of live and git:
  nothing live is removed, its owner decides later) and the next hourly run carries on by itself.
- `refused` (exit 4, `Tier0EdgeGrantsNeedHuman` / `Failed`): `the change against the LIVE policy holds more (or less) than the job's own grants and tests`, the reconciler's classify/guard, a duplicate key in the policy (Python and
  Tailscale may read it differently), or Tailscale's validate.
- `PR flow failed` (exit 5): CI red or silent, a refused merge: the PR is closed, the next attempt waits 6 h, 18 h, a day. `closed N stale automatic PR(s)`: a previous run died mid-flight.
- `PR flow interrupted from outside` (exit 5, `interrupted` in the result): the run got SIGTERM (CT108 is HALTED every night at 01:30 UTC by its Proxmox backup `ct108-nightly` and is back after 10-60 minutes, so
  the 02:20 slot is usually lost and a PR flow started at 01:20 is cut; a reboot or `systemctl stop` look the same). The PR is closed and its branch deleted, the attempt stays on record (2 a day, 2 h apart) but it is NOT a
  failure: no growing wait, the first run after the boot goes on. (If the network were already gone, the stale-PR rule closes the PR on a later run.)
- `could not run` (exit 3): no fresh input (the edge-compat check failing or stale), Prometheus, the clone, `gh` or git cannot push, an installed file differs from main.
A runtime whose sockets cannot be listed (ssh down, timeout) is only `unverified`: nothing is granted for it, the other runtimes carry on.

**Drill (no PR, no GitHub write, no state, no metrics):** `tier0-edge-grants.sh --dry-run --inject FILE` with FILE = `[["100.102.176.103",18002,2],["100.64.0.24",3401,2]]` (ports that listen on a runtime and are not
explicitly granted: `ss -ltn` there; the third number is the closed streak) runs decide + the live validation and prints `dry run: would open a PR`. To prove the unit's own clean environment, run it as
`systemd-run --wait --collect --pipe -p Environment=HOME=/root /usr/local/bin/tier0-edge-grants.sh --dry-run --inject FILE`.

**What stays a person's decision:** the grants accumulate (one small grant per run, never edited): consolidate them now and then by editing the policy by hand and running `scripts/tailscale-policy-ct108.sh plan` / `apply`
(a consolidation is a removal plus an addition, so the reconciler will not do it); anything the job refuses; the hypervisor ssh/8006 mesh and every other grant on a management port. A test that reads `policy.hujson` must not assume
it holds none of the job's blocks (the repo's CI runs the tests on the job's own PR: `tests/test_standby_edge_grants_job.py` runs its policy-edit tests on a policy that already holds earlier blocks).
Exit codes of the job: 0 nothing to do / waiting / merged / dry run / rehearsal, 3 could not run, 4 refused (cap, validation), 5 the PR flow failed.

**The review (2026-10-19).** A fresh agent attacked the first version (1,200 hostile closed lists: nothing could widen the envelope) and found it unfit to run unattended: its first PR turned its own CI red (a test counted the job's
own comment), failures were not rate-limited (a PR and two CI runs an hour), it judged main->new while the reconciler judges live->main (the reconciler would block at 6 grants), it ran unreviewed main as root with the policy
credential, trusted any scraped series and a NaN or negative age, wedged on a stuck PR, merged on the first fast check, and had unbounded port ranges, an unvalidated state file, an unchecked `mktemp` (a clone into `/repo`) and
3389 refusing the whole batch. All of it is fixed above and each point is pinned by a test (`tests/test_standby_edge_grants_job.py`, `test_tier0_edge_grants_wrapper.py`, `test_tier0_edge_grants_install.py`); the edge-side half
(an answer for a pair nobody asked about) is in fleet-state `tier0-edge-compat.sh`.
