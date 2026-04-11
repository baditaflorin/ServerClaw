# ADR 0149: Semaphore For Ansible Job Management UI And API

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.158.0
- Implemented In Platform Version: 0.130.7
- Implemented On: 2026-03-25
- Date: 2026-03-25

## Context

The platform now has multiple repo-managed Ansible converge paths, but it still lacks a dedicated browser-first job console for launching and reviewing bounded Ansible runs.

CLI-first automation remains the canonical path, yet there is value in a private operator surface that can:

- present recent task history and output without ad hoc SSH sessions
- expose a narrow HTTP API for governed job execution
- seed explicit, repo-managed job definitions instead of asking operators to invent runtime state in the UI

Windmill already covers broader workflow orchestration, but it is not optimized for direct Ansible project, inventory, and template management. Semaphore is.

## Decision

We will deploy Semaphore privately on `docker-runtime` with a PostgreSQL backend on `postgres` and a Tailscale-only host proxy on the Proxmox node.

Initial implementation scope:

1. the runtime is deployed through repo-managed Ansible under [playbooks/semaphore.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/semaphore.yml)
2. runtime secrets are injected through the existing OpenBao agent Compose pattern
3. controller-local bootstrap artifacts are mirrored under `.local/semaphore/`
4. a repo-managed `LV3 Semaphore` project is seeded automatically with a local-repository checkout, a localhost inventory, and a `Semaphore Self-Test` Ansible template
5. governed machine access is exposed through [scripts/semaphore_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/semaphore_tool.py), not through broad undocumented API use

## Consequences

- Operators gain a private UI and API for bounded Ansible job execution without changing git and Ansible as the source of truth.
- The platform gains a durable HTTP surface for launching pre-defined Ansible tasks and reading their output.
- Secret scope remains deliberately narrow in the first rollout because the seeded project only runs a localhost self-test job.
- Broader “run the whole platform from inside Semaphore” ambitions remain possible later, but they require explicit inventory, SSH credential, and controller-local secret design.

## Boundaries

- Semaphore must not become the primary place where infrastructure definitions are created.
- Public exposure is out of scope.
- The first live rollout does not claim that all existing repo converges are runnable from inside Semaphore.
- Any later expansion of Semaphore-managed job scope must document how guest SSH, Proxmox-host access, and controller-local secret dependencies are handled.

## Sources

- [Semaphore README](https://github.com/semaphoreui/semaphore/blob/develop/README.md)
- [Semaphore API documentation](https://github.com/semaphoreui/semaphore/blob/develop/api-docs.yml)

## Implementation Notes

- The live implementation will use [roles/semaphore_postgres](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/semaphore_postgres) and [roles/semaphore_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/semaphore_runtime).
- Project, inventory, template, and API-token bootstrap are handled through [platform/ansible/semaphore.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/platform/ansible/semaphore.py) and [scripts/semaphore_bootstrap.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/semaphore_bootstrap.py).
- The initial seeded verification path is the repo-managed [playbooks/semaphore-self.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/semaphore-self.yml) template, which proves UI/API task execution without silently expanding infrastructure credential scope.
- Repo implementation landed in repository release `0.158.0` after rebasing onto current `main`, hardening the bootstrap and runtime idempotency paths, and passing the Semaphore-specific validation stack.
- The integrated mainline live apply for repository release `0.158.0` completed on 2026-03-25: `make converge-semaphore` succeeded from the clean integration worktree, the private Tailscale proxy answered on `http://100.64.0.1:8020/api/ping`, and the seeded `Semaphore Self-Test` template completed successfully through the Semaphore task runner.
- The mainline live apply advances platform version `0.130.7` and includes the durable clean-worktree credential recovery path for future Semaphore bootstrap reruns.
