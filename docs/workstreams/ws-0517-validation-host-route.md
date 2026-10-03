# WS-0517: Restore the remote validation-host route

## Status

`in_progress`. The configured gateway pointed to `ops@10.10.10.30` through
`ops@100.64.0.1`. Those values no longer identify the validation host or a
reachable jump. Live Proxmox inspection confirmed VM 130 `docker-build` at
`10.10.10.30`; the `ops` account, configured bootstrap key, and workspace are
available through the existing `operator-bastion` SSH alias. The target's SSH host
key matches the controller's existing `known_hosts` entry.

The old `10.10.10.30` address reaches a different production machine from the
0docker network, so it must not be used as a fallback validation target.

## Scope

Align `config/build-server.json` and `inventory/build_server.yml` with the
current `docker-build` guest, use the verified bastion alias, preserve normal
host-key verification, and update the remote-build runbook. Bound the full
pre-push gate to two concurrent checks on the shared validation VM. Add
regression tests for the route, pinned host-key policy, and concurrency cap.
Map the deployment-specific alias to a generic name in the public publication
sanitizer.

No server-side account, key, or service changes are needed; the corrected route
authenticates with the existing scoped bootstrap key.

## Verification

- SSH through `operator-bastion` reached `docker-build` as `ops`; the configured
  workspace exists and its host key matches the controller's pinned entry.
- `make check-build-server` passed, including its immutable snapshot upload
  dry-run.
- The Ansible connectivity probe passed (`ansible -i inventory/build_server.yml
  build -m ping`). One initial attempt hit a transient SSH banner timeout; an
  immediate verbose retry connected and returned `pong`.
- `tests/test_build_server_route.py` passed (2 tests).
- Defer the full remote validation workload while the builder is resource
  constrained. At inspection it had load averages above 30, about 545 MiB of
  available memory, and 86% disk usage. Do not run a full gate until capacity
  improves; no cleanup or process termination is in scope.
- The gate selects 24 checks for this change. Its first full-gate attempt was
  stopped before completion while competing Woodpecker jobs were active;
  capacity probes during that contention reached load averages up to 54 and
  available memory as low as 330 MiB. The configured native and fallback gates
  now cap concurrency at two; the complete gate must still pass before the
  branch can be pushed.
- The configured Plane API endpoint timed out during the required workstream
  sync. No Plane issue ID was recorded; the active workstream YAML is the
  authoritative fallback until Plane becomes reachable.
- No numbered release or version bump is prepared: the release manager
  reports 63 existing release blockers and refuses to cut a release. The
  change remains recorded under `Unreleased`.
- Merge through the private repository PR workflow, then publish the
  sanitized ServerClaw snapshot using the repository's publication pipeline.
