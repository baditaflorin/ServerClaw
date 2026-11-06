# apikey-wave: pool replicas move to their local keystore node

What it is. About 385 pool replicas on the infer, 0mcp and 0own runtime hosts verify API keys through `https://apikey-service.0exec.com`, that is through the
dockerhost edge and the dockerhost writer. `apikey-wave` (fleet-state `scripts/ct108/apikey-wave.py`, installed by hand on the builder CT108, systemd
`apikey-wave.timer` every 5 minutes after the last run) adds `APIKEY_SERVICE_URLS=<local node>,<edge>` to the pool's `target_env[<target>]` in
`/root/fleet-state/service-pools.json` and runs `fleet-runner deploy-pool <repo>`, one pool at a time, busiest first. The client asks the local node first and
hedges to the edge after 300 ms. Background, canary proof and plan: claude_team `KEYSTORE-MESH-PLAN-2026-10-15.md` sections 32 and 33.

## Look

```
python3 /usr/local/bin/apikey-wave.py --status          # done count, pending (keys set), deferred, halted
tail /root/fleet-state/state/apikey-wave/events.jsonl    # run-end, keys-set, deploy-start, done, deferred, halt
ls /root/fleet-state/deploy-logs/apikey-wave/            # one deploy-pool log per attempt
```

Metrics (textfile on the builder): `fleet_apikey_wave_pools{state=total|done|pending|deferred}`, `fleet_apikey_wave_halted`,
`fleet_apikey_wave_last_run_timestamp_seconds`.

## Alerts (config/prometheus/rules/fleet-apikey-wave.yml)

- `ApikeyWaveHalted`: the tool stopped itself. `--status` shows `halted.slug` and `halted.reason`. It already reverted the keys it had set but not rolled. Read the
  pool's last log, fix the cause (a failed container, a failed roll), then `python3 /usr/local/bin/apikey-wave.py --resume`.
- `ApikeyWaveSilent`: no run for 3 hours while pools remain: `systemctl status apikey-wave.timer apikey-wave.service`, `journalctl -u apikey-wave.service`.
- `ApikeyWaveStalled`: no pool done in 24 hours. Environmental refusals (Fleet Graph `/brief` timing out under load) cost nothing and are retried every 30 minutes,
  with a 20 minute cooldown after three in a row; `events.jsonl` shows the `error` of each refusal. Check first that it is true: on 2026-10-22 it fired from 22:03Z for a wave that had
  done 82 pools, because for 20 minutes after the builder's nightly backup stop (01:30Z) the scrape target carried `identity="stale"` and a second series of `done` was written under that label;
  its flat samples gave `delta(done[24h]) == 0`. The rule now merges the series first (`delta(max by (instance, host) (fleet_apikey_wave_pools{state="done"})[24h:5m])`), so run that
  expression (or `--status`) before looking for a cause on the builder.

## Gates and switches

- Gates per pool: dockerhost load1 below 80 and fewer than 50 blocked tasks, not inside UTC 01:10-03:05 (the CT108 backup), the keystore node of each target answers `/health`.
- Pause: `touch /root/fleet-state/state/apikey-wave/PAUSE` (remove to continue). Stop for good: `systemctl disable --now apikey-wave.timer`.
- Undo one pool: remove `APIKEY_SERVICE_URLS` from its `target_env[<target>]` in `service-pools.json` under `flock /root/fleet-state/state/pool-guardian/lock`
  (key-level, never copy a whole-file backup back), then `fleet-runner deploy-pool <repo>`.
- The plan is data: `/root/fleet-state/state/apikey-wave/plan.json` (`[{slug, repo, targets}]`, in the order to roll).
