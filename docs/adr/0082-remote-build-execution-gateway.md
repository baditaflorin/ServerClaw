# ADR 0082: Remote Build Execution Gateway

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

All CI-adjacent tasks — Ansible lint, YAML lint, Python type checking, schema validation, pre-commit hooks, Packer builds, Docker image builds — currently run on the operator's laptop. This creates three concrete problems:

1. **CPU contention**: each validation run competes with browser, editor, and OS processes; a full `make validate` on a large repo causes thermal throttling and audible fan spin-up within seconds.
2. **Slow feedback loop**: Ansible lint alone takes 40–90 seconds on a single core. Pre-commit hooks add another 20–30 seconds per push. Operators start skipping checks.
3. **Non-reproducibility**: tool versions differ between the laptop and any future CI agent. Linting passes locally but would fail on a clean runner.

The platform already includes a dedicated build server (`build-lv3`) provisioned with significant compute: 8+ vCPUs, 32 GB RAM, fast local NVMe, and Docker installed. This machine is idle during the vast majority of operator sessions. Its only scheduled work is Docker image pulls and periodic backup verification — both low-intensity.

The gap is a well-defined routing layer: a local `make` target or pre-commit hook that transparently offloads a command to the build server over SSH and streams output back to the operator's terminal. This is different from full remote CI (which Windmill already handles). The goal is **interactive developer ergonomics** — the operator types `make lint` and gets back results in 8 seconds instead of 60, without changing their workflow.

## Decision

We will implement a **Remote Build Execution Gateway** consisting of:

### 1. SSH remote execution wrapper (`scripts/remote_exec.sh`)

```bash
#!/usr/bin/env bash
# Usage: remote_exec.sh <command-label> [--local-fallback]
# Syncs the repo to the build server and runs the command there.
# Streams stdout/stderr back. Exit code is forwarded.
```

The wrapper:
- rsyncs only changed files (using `rsync --checksum --delete`) to `build-lv3:/opt/builds/proxmox_florin_server/`
- runs the requested command on the build server inside a project-pinned Docker container (see ADR 0083)
- streams output back over the same SSH pipe (`ssh build-lv3 "..."`)
- forwards the remote exit code so `make` targets honour it correctly
- falls back to local execution if `build-lv3` is unreachable and `--local-fallback` is set

### 2. `make remote-*` targets in `Makefile`

| Target | Remote command |
|---|---|
| `make remote-lint` | ansible-lint + yamllint + flake8 |
| `make remote-validate` | full schema + data-model validation |
| `make remote-pre-push` | complete pre-push gate (lint + validate + test) |
| `make remote-packer-build IMAGE=<name>` | Packer build on the build server |
| `make remote-image-build SERVICE=<name>` | Docker image build |

All `remote-*` targets call `scripts/remote_exec.sh` with the matching inner command.

### 3. Build server host entry in inventory

```yaml
# inventory/build_server.yml
build_server:
  hosts:
    build-lv3:
      ansible_host: 100.x.y.z        # Tailscale IP
      ansible_user: ops
      ansible_ssh_private_key_file: ~/.ssh/id_ed25519
```

### 4. Rsync workspace conventions

- remote workspace root: `/opt/builds/proxmox_florin_server/`
- secrets (`.local/`, `*.vault`, `.env`) are **never** synced; `.rsync-exclude` lists them explicitly
- the remote workspace is treated as ephemeral; the build server is never the source of truth

### 5. `config/build-server.json` — build capability manifest

Records what the build server can run, pinned tool versions, and available Docker images for each command class. Used by `scripts/remote_exec.sh` to pick the right container.

## Consequences

**Positive**
- Full `make lint` + `make validate` drops from ~90 s to ~8 s from the laptop's perspective (SSH + rsync overhead is ~3 s; the check itself runs in parallel on 8 cores)
- Reproducible: same Docker image on the build server and in Windmill CI
- Laptop CPU/fan stays quiet during routine development
- `--local-fallback` preserves offline-capable workflow (flights, travel, disconnected network)

**Negative / Trade-offs**
- Requires Tailscale reachability to `build-lv3` for the fast path; degraded but functional without it
- rsync adds 1–3 s per invocation even for no-change runs; this is acceptable for a lint gate but not for watch-mode workflows
- Build server must have the project Docker images pre-pulled (addressed by ADR 0089 build cache)

## Alternatives Considered

- **GitHub Actions / external CI**: adds cost, requires internet, cannot access private Proxmox inventory; unsuitable for a private homelab IaC repo
- **Devcontainer on the laptop**: moves work to a container but still consumes local CPU; does not solve the thermal problem
- **Windmill for every check**: Windmill CI is appropriate for post-merge gates but introduces too much latency (~30 s workflow startup) for interactive development

## Related ADRs

- ADR 0083: Docker-based check runner (defines the containers remote_exec.sh invokes)
- ADR 0084: Packer template pipeline (uses `make remote-packer-build`)
- ADR 0087: Repository validation gate (pre-push hook delegates to this gateway)
- ADR 0089: Build artifact cache (keeps Docker images warm on the build server)
- ADR 0090: Platform CLI (exposes `lv3 lint`, `lv3 validate` over this gateway)
