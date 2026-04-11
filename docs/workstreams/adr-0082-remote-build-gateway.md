# Workstream ADR 0082: Remote Build Execution Gateway

- ADR: [ADR 0082](../adr/0082-remote-build-execution-gateway.md)
- Title: Offload CPU-intensive checks and builds to the build server over SSH with rsync workspace sync
- Status: live_applied
- Branch: `codex/adr-0082-remote-build-gateway`
- Worktree: `../proxmox-host_server-remote-build-gateway`
- Owner: codex
- Depends On: none (foundational)
- Conflicts With: none
- Shared Surfaces: `Makefile`, `scripts/`, `inventory/`, `ansible.cfg`

## Scope

- write `scripts/remote_exec.sh` — rsync workspace to build server, execute command in Docker container, stream output, forward exit code
- add `inventory/build_server.yml` with `build-lv3` host entry (Tailscale IP)
- write `config/build-server.json` — build capability manifest: host, SSH key path, workspace root, available command classes
- add `make remote-lint`, `make remote-validate`, `make remote-pre-push`, `make remote-packer-build`, `make remote-image-build` targets
- write `.rsync-exclude` listing all secret paths that must never sync to the build server (`.local/`, `*.vault`, `.env`, `receipts/`)
- write `docs/runbooks/remote-build-gateway.md` — setup, usage, fallback mode, troubleshooting
- add `make check-build-server` target that verifies SSH connectivity and workspace sync health

## Non-Goals

- replacing Windmill CI (this is for interactive developer ergonomics, not post-merge gates)
- implementing the Docker containers (ADR 0083)
- managing build server provisioning as a Packer template (ADR 0084)

## Expected Repo Surfaces

- `scripts/remote_exec.sh`
- `inventory/build_server.yml`
- `config/build-server.json`
- `.rsync-exclude`
- updated `Makefile` (6 new remote targets)
- `docs/runbooks/remote-build-gateway.md`
- `docs/adr/0082-remote-build-execution-gateway.md`
- `docs/workstreams/adr-0082-remote-build-gateway.md`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-build` reachable through the current Proxmox host jump path and responsive to `make check-build-server`
- `make remote-lint` completes in < 20 s from the laptop

## Verification

- `make check-build-server` passes (SSH + rsync connectivity verified)
- `make remote-lint` streams ansible-lint output from build server and returns exit code correctly
- `make remote-lint` with `build-lv3` offline falls back to local execution with a visible warning
- `.rsync-exclude` verified: running `make remote-lint` does not copy `.local/` to the build server (confirmed via `rsync --dry-run -v`)

## Merge Criteria

- `scripts/remote_exec.sh` handles SSH failures and rsync errors with clear error messages and correct exit codes
- all 5 remote `make` targets pass end-to-end test from a clean laptop with Tailscale active
- `.rsync-exclude` reviewed and approved to ensure no secrets are synced

## Notes For The Next Assistant

- the rsync must use `--checksum` rather than `--times` because the worktree workspace may have newer mtimes on files that haven't actually changed
- use `ssh -o ConnectTimeout=5 -o BatchMode=yes` in the connectivity check to fail fast when the build server is unreachable
- `scripts/remote_exec.sh` should print the exact `docker run` command it will run on the remote server when `REMOTE_EXEC_VERBOSE=1` is set — this is critical for debugging check failures

## Delivered

- added `scripts/remote_exec.sh` with managed SSH connectivity checks, rsync sync, dry-run health verification, and local fallback support
- added `config/build-server.json`, `inventory/build_server.yml`, and `.rsync-exclude` as the repo-managed build-gateway contract
- appended the `Makefile` remote execution targets and documented the operator flow in `docs/runbooks/remote-build-gateway.md`
- added regression coverage for docker-runner selection, local fallback behavior, and the rsync dry-run health check
- verified the live SSH route through `ops@100.118.189.95` to `ops@10.10.10.30` and captured that jump-path contract in the gateway config

## Repo Implementation Notes

- Repo implementation first landed on `2026-03-23` in release `0.80.0`.
- Live apply completed on `2026-03-23` for platform version `0.38.0`.
- `make check-build-server` now passes against the real `docker-build` route, and `rsync` is part of the canonical build-guest package list so future guest convergence preserves that requirement.
