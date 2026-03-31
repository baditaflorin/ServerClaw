# Remote Build Gateway

## Purpose

ADR 0082 introduces a controller-side gateway that syncs this repository to the build server and runs heavy validation or build commands there instead of on the operator laptop.

The laptop remains the editor and orchestrator. The build server becomes the CPU-heavy execution surface.

## Repository Surfaces

- `scripts/remote_exec.sh`
- `config/build-server.json`
- `config/validation-runner-contracts.json`
- `.rsync-exclude`
- `inventory/build_server.yml`
- `Makefile`

## Prerequisites

1. The build server is reachable over SSH as `ops`.
2. `config/build-server.json` points at the correct host, key path, and jump-path SSH options.
3. `.rsync-exclude` is reviewed so secrets never leave the controller.
4. The build server has `rsync`, `bash`, and whichever toolchain the selected command needs.
5. If you want containerized execution, the corresponding runner image metadata exists in `config/check-runner-manifest.json`.
6. The selected command's `runner_id` and `local_fallback_runner_id` both resolve in `config/validation-runner-contracts.json`.

## Initial Setup

Update the build-server host settings:

```bash
$EDITOR config/build-server.json
$EDITOR inventory/build_server.yml
```

On the current live platform the build VM does not have a controller-reachable Tailscale IP of its own. The verified route is:

- controller bootstrap key: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`
- jump host: `ops@100.64.0.1`
- build VM target: `ops@10.10.10.30`
- remote workspace root: `/home/ops/builds/proxmox_florin_server`
- remote session checkout layout: `/home/ops/builds/proxmox_florin_server/.lv3-session-workspaces/<session_slug>/repo`
- immutable run namespace layout: `/home/ops/builds/proxmox_florin_server/.lv3-session-workspaces/<session_slug>/repo/.lv3-runs/<run_id>/repo`

Confirm the gateway can reach the server and dry-run a workspace sync:

```bash
make check-build-server
```

## Daily Usage

Interactive lint on the build server:

```bash
make remote-lint
```

Full validation on the build server:

```bash
make remote-validate
```

That run now records `.local/validation-gate/remote-validate-last-run.json` in the local checkout after the build-server copy is synced back. The payload includes:

- the selected validation runner id
- the declared capability contract for that runner
- the per-run environment attestation for architecture, tooling, container runtime, network class, and scratch-space guarantees

The `remote-validate` path now also includes ADR 0306 `iac-policy-scan`, so the
build server proves the same Checkov-backed IaC policy contract that the local
pre-push gate uses.

Run the full pre-push gate remotely, but allow local fallback if the build server is offline:

```bash
make remote-pre-push
```

Run an arbitrary shell command remotely:

```bash
make remote-exec COMMAND="uname -a"
```

Inspect the exact `docker run` command the gateway would execute when runner metadata is present:

```bash
REMOTE_EXEC_VERBOSE=1 make remote-lint
```

Run a remote command under a human-readable session namespace:

```bash
LV3_SESSION_ID=debug-grafana make remote-lint
```

## Fallback Mode

If the build server is unavailable, add `--local-fallback` through the make target or call the script directly:

```bash
scripts/remote_exec.sh remote-lint --local-fallback
```

Fallback mode intentionally runs the repo-defined local command, not the remote Docker path.

When the wrapper falls back locally, it now switches `LV3_VALIDATION_RUNNER_ID` to the command's declared `local_fallback_runner_id` before executing the repo command. That keeps the recorded status payload and gate attestation honest about which runner actually executed the validation.

When that local command re-enters the repo through `bash -lc`, the gateway now exports `LV3_VALIDATE_PYTHON_BIN` from the invoking shell when it can. `scripts/validate_repo.sh` then resolves its direct Python validators against that Python 3.10+ interpreter so local fallback does not silently regress to the login shell's default `python3`.

## Snapshot Safety Contract

The remote workspace root is ephemeral and never authoritative.

Each remote run now builds one immutable content-addressed snapshot locally,
uploads the snapshot archive to the active session workspace, and unpacks it
into a fresh `.lv3-runs/<run_id>/repo` namespace before the remote command
starts.

The stable session root still lives beneath `.lv3-session-workspaces/`, but the
repo payload used by validation and build commands is no longer a mutable
`rsync` mirror.

The snapshot excludes:

- `.local/`
- `*.vault`
- `.env`
- `receipts/`
- `.git/`
- Python caches and local build caches

Review `.rsync-exclude` before adding any new local secret material.

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `build server ... is unreachable` | wrong host, key, or Tailscale path | run `make check-build-server`, then verify `config/build-server.json` |
| `build server ... is unreachable; controller appears logged out...` | the local workstation is no longer enrolled in the Headscale-managed mesh | check `'/Applications/Tailscale.app/Contents/MacOS/Tailscale' status`, re-authenticate the workstation to `https://headscale.lv3.org`, and confirm `ops@100.64.0.1` works again before retrying |
| host is reachable but the build VM is not | missing or broken ProxyCommand jump path | verify the Proxmox host hop to `100.64.0.1` and the guest target `10.10.10.30` |
| rsync fails before SSH starts | missing `rsync` locally or remotely | install `rsync` on both ends |
| command runs remotely but not in Docker | runner manifest missing for that label | add `config/check-runner-manifest.json` in ADR 0083 or keep using shell mode |
| a gate payload reports `runner_unavailable` | the selected runner contract does not satisfy the requested lane, or the attested Docker/tooling/runtime state was unavailable | inspect `.local/validation-gate/*.json`, then compare the `runner.capability_contract` and `runner.environment_attestation` blocks |
| local fallback runs unexpectedly | SSH connectivity probe failed | inspect key permissions, host reachability, and `ConnectTimeout=5` behavior |
| local fallback fails on `int | None` or another modern type annotation | the login shell resolved an older Python for direct validators | export `LV3_VALIDATE_PYTHON_BIN=/absolute/path/to/python3.10+` and rerun |
| snapshot upload fails before the remote command starts | missing `rsync`, a full remote disk, or a permission problem in `.lv3-snapshots/` | rerun `make check-build-server`, confirm the session root is writable, inspect `.lv3-session-workspaces/` usage, and clean stale session directories or unused Docker artifacts if the build VM is full |
| snapshot unpack fails on the build server | missing `tar`, corrupted upload, or a stale partial run namespace | remove the affected `.lv3-runs/<run_id>` directory and retry from the current worktree |
| secrets appear in remote dry-run output | `.rsync-exclude` is incomplete | stop and update `.rsync-exclude` before re-running |

## Notes

- `check-build-server` is intentionally a dry-run snapshot upload plus SSH health check. It should be safe to run repeatedly.
- the gateway preserves a stable session namespace per checkout by default; set `LV3_SESSION_ID` when you need a human-readable namespace for debugging or live verification
- if remote disk pressure is caused by abandoned `.lv3-session-workspaces/<session_slug>` roots, delete only inactive session directories after confirming no active `remote_exec.sh`, `rsync`, or runner process still references them; root-owned runner artifacts may require `sudo`, and every manual cleanup should be recorded in the matching live-apply receipt
- ADR 0266 adds runner capability contracts and per-run attestation on top of ADR 0083. Commands without runner metadata still execute as managed remote shell commands, but the governed validation paths now record the runner identity they actually used.
- normal remote runs prune session directories older than two days and also cap retained session roots, run namespaces, and snapshot archives so a high-concurrency validation day does not indefinitely grow the build-server workspace. Override the defaults with `REMOTE_EXEC_SESSION_KEEP_COUNT`, `REMOTE_EXEC_RUN_KEEP_COUNT`, or `REMOTE_EXEC_SNAPSHOT_KEEP_COUNT` only for operator debugging.
