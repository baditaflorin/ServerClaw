# WS-0517: Restore the remote validation-host route

## Status

`merged`. The configured gateway pointed to `ops@10.10.10.30` through
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
- Focused regression suite passed: 11 tests across the remote-route and
  publication-sanitization checks. JSON validation and formatting checks passed.
- The complete pre-push gate passed. The shared validator became overloaded
  during its run (load peaked above 145 and available memory fell below 1 GiB),
  so only this gate's process groups were stopped; the required local fallback
  then passed all selected checks, including Ansible lint/syntax, IaC policy,
  security, Semgrep, schema, generated-artifact, and workstream-ownership checks.
- Private PR #266 merged on 2026-10-03 at
  `0fd430749467ce58041d6ad2ca822705be18cee6`; both required Woodpecker push and
  PR checks passed.
- The sanitized-publication coverage audit and leak scan passed. The publisher
  replaced five deployment-specific files, deleted two private-only paths,
  sanitized 3,959 files, and regenerated public derived artifacts. ServerClaw
  PR #67 merged on 2026-10-03 at
  `f02a428356a08353877a2b4170b94a30ca374454`; both Woodpecker checks passed.
- Plane synchronization was attempted for the merged workstream, but the
  configured API endpoint did not establish a TCP connection; no Plane issue
  ID was created. Git remains authoritative, as documented by ADR 0360.
- This workstream changes validation routing/configuration only; it did not
  change service credentials, user accounts, or running service workloads.
- The release bump remains pending the repository's governed release flow;
  `canonical_truth` records the patch note for that flow.
