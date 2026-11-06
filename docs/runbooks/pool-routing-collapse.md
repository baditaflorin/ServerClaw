# The pools' replicas stopped taking traffic (FleetPoolReplicaShareCollapsed)

## What the alert says

More than 5 pools carry traffic and send under 5 % of it to their replicas although their weights give the replicas more than 30 %, for 30 minutes, while the balancer file is fresh
(written in the last 30 minutes). Per pool the balancer measures the share of requests that went to each member over the last hour
(`fleet_pool_balance_member_measured_share_pct{service,target}`, it exists only for pools with at least 20 requests in that hour) and knows what the weights give that member
(`fleet_pool_balance_member_configured_share_pct`); the alert sums both over the members that are not the Docker host (`target!="dockerhost"`: the Docker host's own share rises
when the replicas stop taking traffic and would mask the collapse). In normal times 1-4 pools are in that state; on 2026-10-22 the count was 120 at the busiest, 8 at low traffic, 1 after the restore.
Nothing else in the pool tooling looks wrong when this happens: the pools are healthy, the guardian has no finding, the balancer proposes nothing, because only the **route** from the gateway
to the pools is gone.

To list the pools, on the monitoring Prometheus (the alert's condition without the count):
`(sum by (service) (fleet_pool_balance_member_measured_share_pct{target!="dockerhost"}) < 5) and on (service) (sum by (service) (fleet_pool_balance_member_configured_share_pct{target!="dockerhost"}) > 30)`.

## Reading the number

The share comes from the pool balancer (`fleet-pool-balance.timer` on the builder, textfile `fleet_pool_balance_*`), measured over a 1 hour window, and the file is rewritten only when a balancer run ends.
Two consequences, both seen on 2026-10-22: after a restore the count falls for about an hour (a few minutes of "still counted" is the window catching up, not a second collapse), and while
the pool guardian holds the shared pool lock (its runs took about 31 minutes) the balancer logs "another run holds the lock; nothing to do" and the numbers freeze at their last value; look at
`fleet_pool_balance_last_run_timestamp_seconds` before trusting a value. That is why the alert needs a file written in the last 30 minutes: a frozen file does not alert, `FleetPoolBalanceSilent`
and `FleetPoolBalanceNotReporting` (fleet-loops.yml, after an hour) are the alerts for a balancer that stopped writing.

**A few pools can be the start of a bigger bypass (2026-10-26/27).** At about 02:14Z the count went from 3 to 16 and stayed there for hours. I took it for pools whose only traffic was internal probes (0.02-0.074 requests a second) and put a traffic floor on this alert (#588, 10-26); that was wrong and is reverted. Those 16 were the first pools of a **colocation bypass**: the `domainscope-api` container on docker-prod (10.10.10.30, `/opt/domainscope_scrapetheworld.org/.env`) had `FLEET_COLOCATE_SERVICES` set to a list of service ids (3 before, 124 afterwards), so its calls go straight to the Docker host copy of each listed pool and the replicas only answer the gateway's `/health`. The count then rose 16 -> 21 (09:59Z) -> 98 (10:59Z) -> 113 (12:29Z) of 132 measured pools, and `FleetHostOverloaded` followed on the 0docker hypervisor, because the Docker host carried all of the pooled load. With the floor this alert was silent for the first eight hours (0-1 pools counted until 10:00Z). Low traffic is not a reason to ignore the count: a bypass starts with a few pools.
To tell a bypass from a dead pool, read the members' own counters: scrape `/metrics` of the Docker host copy and of one replica at their published addresses twice, two minutes apart, and diff `http_requests_total` (or `http_request_duration_seconds_count`) by `route`. Non-health requests growing on the Docker host copy only, while the gateway's own `/health` checks split by the weights, is a bypass: the pool is healthy and routing is right, the callers do not use it. Check `FLEET_COLOCATE_SERVICES` of the callers (`domainscope-api`, `docker exec ... printenv FLEET_COLOCATE_SERVICES`, the ids only) and ask the DomainScope release sessions whether the list is intended before changing production env.

Why a count of pools and not an average: the first version of this alert compared the average replica share with half of its highest value of the last 24 hours and raised a false alarm at 18:51Z
on 2026-10-22, because only pools with at least 20 requests in the window have a share, and that set fell from 131 pools to 10 when the bulk scan that produced the traffic ended, so the average
and its baseline described different sets of pools. A count of pools that individually look collapsed does not depend on how many pools carry traffic (back-tested on the 24 hours around the
incident: true only from 10:05Z to 14:35Z, never in the healthy hours).

## FleetPoolBalanceStuck (the second signature)

More than 30 pools have a routing proposal, apply is on, the balancer ran in the last 30 minutes and applied nothing for 2 hours. On 2026-10-22 (10:31-14:31Z) `fleet_pool_balance_proposals_pending`
was 200-257 against a normal 3-5 and `fleet_pool_balance_applied` was 0, because every proposal was skipped with "the gateway does not match what is rendered today ... a render is pending, left
to whoever owns that render". Look at `grep balance_skipped /root/fleet-state/state/pool-guardian/events.jsonl | tail` on the builder, then the read-only `nginx-render` of "Check" above. Other causes:
a guard that refuses every pool (environment contract, cordon) or the load gate. A frozen file does not alert (the freshness term): `FleetPoolBalanceSilent` and `FleetPoolBalanceNotReporting` own that.

## FleetPoolBalanceEnvGuardHolding (the third signature)

In at least 6 of the last 8 hours, a full planning run of the balancer left more than 40 % of the pools where they were because of the environment contract guard
(`fleet_pool_balance_skipped_env_contract` over `fleet_pool_balance_pools`, hourly maximum). Nothing is down: a pool that cannot be balanced keeps its old split, so replica load stops being
rebalanced. `FleetPoolBalanceStuck` does not see it, because the quick batch runs between the full runs keep applying a few pools (`fleet_pool_balance_applied` stays above 0).
The number needs go_fleet_runner >= v0.7.717 on the builder; a runner without it publishes nothing and this alert stays quiet.

**What it was on 2026-10-24/25.** The keystore wave (`apikey-wave`) set `APIKEY_SERVICE_URLS` on the remote copies of a pool before the dockerhost copy. The guard compares the NAMES of the
environment variables of the copies and refuses to move traffic toward a copy that lacks a name another copy has, so for the days the wave ran a full planning run held 66-95 % of the 282 pools
(the event log, which starts 10-24 15:29Z, shows 23 of 27 hours) while 6-37 pools an hour were still applied. Found by counting `balance_skipped` against `balance_applied` per hour, not by an alert.
Fixed by naming the variable in the guard's harmless list (go_fleet_runner v0.7.713): the next balance run applied 40 and held none for that name.

**Check (builder, read-only).** Which names hold pools, per hour:

```
python3 - <<'EOF'
import json, re, collections
c = collections.Counter()
for p in ("/root/fleet-state/state/pool-guardian/events.jsonl.1", "/root/fleet-state/state/pool-guardian/events.jsonl"):
    for l in open(p):
        e = json.loads(l)
        if e.get("kind") != "balance_skipped": continue
        m = re.search(r"only on [^:]+: ([A-Za-z0-9_,]+)", e.get("detail", ""))
        if m: c[(str(e["time"])[:13], m.group(1).split(",")[0])] += 1
for k, n in sorted(c.items()): print(k, n)
EOF
```

The first name of each refusal is the one to look at. Then:

1. A wave is staging a variable that only some copies have: finish the wave (the next full run proceeds), or pause it if the half-done state will last for days.
2. The variable differs by design and a copy works without it (a per-node list, a tuning knob): add it to `balanceHarmlessEnv` in go_fleet_runner `pool_balance.go` (a release and a runner install), or, if
   the per-pool ignore list (go_fleet_runner PR #981) has shipped, name it for the pools that need it.
3. Old, real differences (infer or 0own copies with `BACKOFF_COORDINATOR_URL`, `CALL_TRACER_URL`, `FINGERPRINT_CACHE_URL`, `FLEET_FETCH_CACHE_URL` that the dockerhost copy lacks, about 77 pools) are a standing
   level, and the number held depends on how many pools ask for a shift toward the Docker host: 2-9 when no host is pressured, 90-92 (about a third) while infer-runtime is (measured 2026-10-26 04-05Z).
   That is below the 40 % line (113 pools). Aligning those copies, or declaring the names expected to differ (go_fleet_runner PR #981, a draft waiting for the owner), is a per-pool decision about which copy is right.

Do not turn the guard off to clear the alert: it exists because the 0mcp copies of some proxy-dependent services have no proxy settings and traffic moved onto them goes out without the proxy.

## What it was on 2026-10-22

At 09:06Z a bulk `nginx-render --push --reload` ran from a host that does not hold the private `service-pools.json` (a missing file reads as "no pools").
It rendered all 282 pooled services with the plain single-origin route and pushed them: every `proxy_pass http://fleet_pool_<id>` in
`/etc/nginx/sites-enabled/*.https.conf` became `proxy_pass http://10.10.10.20:<port>` (the Docker host). The average replica share went 86 % -> 4 % in about 80 minutes (the measure
is a rate window; the alert's count of collapsed pools was over 5 from 10:05Z), the Docker host took the whole load again, the standby edge could serve 276 vhosts fewer (`Tier0EdgeCompatServedDrop`, 457 -> 181), and
the balancer logged "the gateway does not match what is rendered today ... a render is pending ... left to whoever owns that render" for every pool with a proposal.
The restore took 30 minutes (the push validates placement per pool, about 6 seconds each). Since go_fleet_runner v0.7.707 `nginx-render --push` refuses such a push (`--allow-unpool`
to override); until the builder runs that version, treat any bulk push outside the builder as suspect.

## Check

1. How many vhosts still route through a pool (on the gateway, as root):
   `grep -l "proxy_pass http://fleet_pool_" /etc/nginx/sites-enabled/*.https.conf | wc -l` (about 282; 0 means the collapse above).
2. On the builder: `fleet-runner nginx-render --service-pools /root/fleet-state/service-pools.json` (read-only). `changed: N` is the number of files that differ
   from what the pools file renders. Add `--exact-filter <names>` to look at specific services; a bulk run also shows unrelated differences (leave those to their owner).
3. The balancer's own words: `grep render /root/fleet-state/state/pool-guardian/events.jsonl | tail -3` ("a render is pending").
4. If the vhosts are fine, look at the replica hosts instead: `fleet-runner pool-status` for the pools with a degraded member, and the hosts' node exporters.

## Restore (builder, root)

1. Read-only first, with the exact list of the pooled services and the live pools file:
   `LIST=$(python3 -c "import json; print(','.join(sorted(json.load(open('/root/fleet-state/service-pools.json'))['services'])))")`
   `fleet-runner nginx-render --exact-filter "$LIST" --service-pools /root/fleet-state/service-pools.json --out /tmp/restore-dry`
   Expect `new: 0` and `changed: <the number of vhosts that lost their pool>`.
2. Push under the balancer's lock, detached (it takes ~30 minutes for 282 pools):
   `setsid nohup flock -w 900 /root/fleet-state/state/pool-guardian/balance.lock fleet-runner nginx-render --exact-filter "$LIST" --service-pools /root/fleet-state/service-pools.json --push --reload > /root/pool-routing-restore.log 2>&1 &`
3. Verify: step 1 of "Check" counts the pooled vhosts again, a sample of `/health` answers 200, the standby's next hourly `tier0-edge-compat` run is back above 450 served vhosts,
   and this alert clears once the balancer has measured the replicas' share again (about 30 minutes).

The gateway keeps the capture of the previous push under `/root/fleet-nginx-rollbacks/<time>/` (full sets for a bulk push, `MANIFEST` maps `route-N` to the file);
a render made with the pools file is byte-identical to what that capture holds for the pooled vhosts, so the capture is a way to check the restore, not something to copy back.

## Do not

- Run a bulk `nginx-render --push` anywhere but the builder, or without `--service-pools` pointing at the live file.
- Use `--allow-unpool` unless the service is meant to leave its pool: edit the pools file first, then push.
