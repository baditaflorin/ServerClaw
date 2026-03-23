# Remote Build Gateway

## Purpose

ADR 0082 introduces a controller-side gateway that syncs this repository to the build server and runs heavy validation or build commands there instead of on the operator laptop.

The laptop remains the editor and orchestrator. The build server becomes the CPU-heavy execution surface.

## Repository Surfaces

- `scripts/remote_exec.sh`
- `config/build-server.json`
- `.rsync-exclude`
- `inventory/build_server.yml`
- `Makefile`

## Prerequisites

1. The build server is reachable over SSH as `ops`.
2. `config/build-server.json` points at the correct host, key path, and jump-path SSH options.
3. `.rsync-exclude` is reviewed so secrets never leave the controller.
4. The build server has `rsync`, `bash`, and whichever toolchain the selected command needs.
5. If you want containerized execution, the corresponding runner image metadata exists in `config/check-runner-manifest.json`.

## Initial Setup

Update the build-server host settings:

```bash
$EDITOR config/build-server.json
$EDITOR inventory/build_server.yml
```

On the current live platform the build VM does not have a controller-reachable Tailscale IP of its own. The verified route is:

- controller bootstrap key: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`
- jump host: `ops@100.118.189.95`
- build VM target: `ops@10.10.10.30`
- remote workspace root: `/home/ops/builds/proxmox_florin_server`

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

## Fallback Mode

If the build server is unavailable, add `--local-fallback` through the make target or call the script directly:

```bash
scripts/remote_exec.sh remote-lint --local-fallback
```

Fallback mode intentionally runs the repo-defined local command, not the remote Docker path.

## Rsync Safety Contract

The remote workspace root is ephemeral and never authoritative.

The sync excludes:

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
| host is reachable but the build VM is not | missing or broken ProxyCommand jump path | verify the Proxmox host hop to `100.118.189.95` and the guest target `10.10.10.30` |
| rsync fails before SSH starts | missing `rsync` locally or remotely | install `rsync` on both ends |
| command runs remotely but not in Docker | runner manifest missing for that label | add `config/check-runner-manifest.json` in ADR 0083 or keep using shell mode |
| local fallback runs unexpectedly | SSH connectivity probe failed | inspect key permissions, host reachability, and `ConnectTimeout=5` behavior |
| secrets appear in remote dry-run output | `.rsync-exclude` is incomplete | stop and update `.rsync-exclude` before re-running |

## Notes

- `check-build-server` is intentionally a dry-run sync plus SSH health check. It should be safe to run repeatedly.
- ADR 0083 extends this gateway with pinned check-runner images. Until then, commands without runner metadata execute as managed remote shell commands.
