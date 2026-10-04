# WS-0518: Restore the governed Plane API access path

## Status

`merged` via private-source PR #268 at `2d43502e1f93e2c11281592390fc56ebcc66324d`. Plane is healthy behind the authenticated public edge. Direct workstation TCP access to the tailnet proxy is filtered before packets reach the host; the loopback-only SSH forward is the verified private API route for governed automation.

## Scope

Keep Plane's public browser path behind Authentik, restore the private API route without exposing Plane publicly, synchronize this workstream into the existing `AW` project, and replace stale/hard-coded access instructions with a generic SSH-forward procedure. No Plane container, database, or server credential was changed.

## Verification

- The public Plane edge redirects unauthenticated browser requests to the shared authenticated entrypoint as expected.
- The private Plane readiness endpoint returned HTTP 200 through `127.0.0.1:18093` while the SSH forward was active.
- The stored Plane API token authenticated successfully; the configured workspace contains its existing `AW` and `ADR` projects.
- This workstream synchronized successfully and has exactly one matching issue in `AW`; a repeat sync updates the same issue.
- Direct tailnet TCP access from the operator workstation was not reaching the host; the SSH forward uses the existing authorized Proxmox ingress and binds only to loopback.
- The API-token-based sync path is healthy. No password reset or Plane user credential change was needed.
- `make plane-manage ACTION=whoami`, project listing, and ADR issue listing succeeded through the loopback forward.
- Private PR #268 passed both required Woodpecker checks (`ci/woodpecker/pr/woodpecker` and `ci/woodpecker/push/woodpecker`) before merge.
- No Plane container, database, server firewall, or tailnet ACL was changed. Direct tailnet TCP remains a separate policy/routing follow-up; the documented SSH route keeps the API private and functional.
- No numbered release was cut. The release manager reports 63 pre-existing readiness blockers, so this change remains under `Unreleased` with `included_in_repo_version: null` until the governed release flow.

## Next

Retain the loopback SSH forward while using local Plane automation. If direct tailnet API access is required later, inspect the active tailnet policy separately; do not expose the unauthenticated API listener publicly. Browser authentication after the Authentik redirect remains an interactive-session check.
