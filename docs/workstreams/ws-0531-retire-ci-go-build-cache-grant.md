# WS-0531: Remove the CI Go build cache grant

## Status

`live_applied`: merged in PR #504 and applied from CT108 by the owner on 2026-10-19 at about
11:25 UTC (the time of the pre-apply rollback copy the tool saved there).

Verified afterwards, from outside the apply:

- `scripts/tailscale-policy-ct108.sh drift` (read-only): no drift. The live policy version
  changed from `002f7909...` (the one with the grant) to `5a5aca95...`.
- A diff of that saved pre-apply policy against git shows the apply removed exactly the
  one grant and its three policy tests. It also made live one grant that is not part of this
  workstream: the Metrics Hub (dockerhost) may scrape the nginx gateway's node exporter,
  TCP 9100 on that one host, from PR #507, which was already on `main` when the apply ran.
- From pve01, 0infer and 0mcp VM 130, TCP connects to the cache port (18335) and its metrics
  port (18336) on the build worker both time out after the full 4 s (curl exit 28, 4010 to
  4020 ms): the tailnet drops them. The cache server is stopped, so a refused connection (exit
  7, fast) would have meant the path was still open; none was. A control to a path that is
  still allowed (the Woodpecker server) connected in 10 to 62 ms.

## Why

WS-0530 opened TCP 18335 on the 0own build worker for the CI agents on pve01, 0infer and
0mcp, so they could use a shared Go build cache. Measured afterwards on a Go build plus test:
slower than no cache over 17 to 38 ms, and on the server's own host no better than a plain
host-mounted cache directory. The server was stopped and nothing listens on 18335 or 18336
any more. The grant would now allow connections to a closed port, which is harmless but
leaves an unused path; the cache server accepted uploads without a token, so the path is not
worth keeping open "just in case".

## Change

- Remove the one grant to TCP 18335 and its three policy tests (accept 18335, deny 18336).
- Nothing else changes.

## Verification

- Offline: `python3 scripts/tailscale_policy_sync.py check`.
- Live validation of the remaining policy tests: `scripts/tailscale-policy-ct108.sh plan` on
  CT108; the plan should show only these four removals.
- Apply after merge: `scripts/tailscale-policy-ct108.sh apply` on CT108.
