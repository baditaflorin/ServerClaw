# WS-0530: CI agents reach the shared Go build cache

## Status

`live_applied`: merged in PR #469 and applied from CT108 on 2026-10-18 at
19:46:59 UTC. The live plan showed only this grant and its three tests; the
Tailscale API validated the policy and its tests; after apply the live policy
equals git (no drift). The rollback copy is in the CT108 state directory.

Verified the same minute from all three agent hosts: the cache port answers over
HTTP, the metrics port times out. Ping round trip to the build worker: about
14 ms from pve01, 18 ms from 0infer, 35 ms from 0mcp.

## Goal

A shared Go build cache server (a `GOCACHEPROG` HTTP backend) runs on the 0own
build worker. Woodpecker agents on the other sites (pve01, 0infer, 0mcp) should
reuse its compiled packages instead of rebuilding them. Those agents reach 0own
only over the tailnet, and today the policy does not let them reach it at all.

## Change

- One grant: the three CI agent tailnet addresses may reach the 0own build
  worker on TCP 18335 (the cache port) only.
- Policy tests for each agent: TCP 18335 is accepted, TCP 18336 (the same
  server's metrics and debug port) is denied.
- Nothing else is opened. The agents still cannot reach each other or any other
  port on the build worker.

## Safety

The cache client used in CI fails open: when the server is down, slow or
unreachable, every lookup is a local cache miss and the build continues. So a
wrong or missing grant makes builds slower, never broken.

## Verification

- Offline: `python3 scripts/tailscale_policy_sync.py check`.
- Live validation of the policy tests: `scripts/tailscale-policy-ct108.sh plan`
  on CT108. Review the plan diff before apply.
- Apply: `scripts/tailscale-policy-ct108.sh apply` on CT108 after merge.
- End to end: from each agent, a TCP connect to the cache port succeeds and a
  connect to the metrics port times out.
