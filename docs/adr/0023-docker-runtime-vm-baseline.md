# ADR 0023: Docker Runtime VM Baseline

- Status: Accepted
- Implementation Status: Partial Implemented
- Implemented In Repo Version: 0.25.0
- Implemented In Platform Version: 0.17.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The current Docker runtime guest exists, but its software baseline is still only whatever cloud-init happened to install during guest provisioning.

Today that means:

- `docker-runtime-lv3` at `10.10.10.20` is present as VM `120`
- guest provisioning currently installs Debian's `docker.io` package
- there is no explicit Docker Compose v2 plugin baseline
- there is no dedicated Docker daemon configuration for service continuity or log retention

That is not a stable production contract. The runtime VM needs an explicit host baseline that can be converged repeatedly and audited from the repository.

## Decision

We will manage the Docker runtime VM with a dedicated runtime baseline role and playbook.

The baseline for `docker-runtime-lv3` is:

1. Install Docker Engine from Docker's official Debian repository.
   - remove conflicting distro packages such as `docker.io`
   - install `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, and `docker-compose-plugin`
2. Treat Docker Compose as the standard runtime orchestrator on this VM.
   - use the Compose v2 plugin through `docker compose`, not the legacy standalone `docker-compose` package
3. Set Docker daemon defaults that are appropriate for long-running workloads.
   - enable `live-restore`
   - keep the default `json-file` log driver
   - enforce log rotation with bounded file size and file count
4. Keep routine administration on the existing named operator account.
   - `ops` remains the routine sudo user
   - `ops` is added to the local `docker` group on this VM for explicit operator workflows
5. Keep this baseline separate from security policy and workload deployment policy.
   - host-level security controls move into a dedicated follow-up ADR
   - application stack layout and systemd-managed compose projects move into a separate follow-up ADR

## Consequences

- Docker installation becomes reproducible and versionable instead of depending on cloud-init side effects.
- Compose support becomes part of the declared runtime contract.
- Container restarts during Docker upgrades become less disruptive because `live-restore` is enabled.
- Container logs stop growing without bounds on the runtime VM.
- Security controls for published ports still need a dedicated follow-up because Docker's networking rules have their own firewall implications.

## Sources

- <https://docs.docker.com/engine/install/debian/>
- <https://docs.docker.com/engine/daemon/live-restore/>
- <https://docs.docker.com/engine/logging/drivers/json-file/>
