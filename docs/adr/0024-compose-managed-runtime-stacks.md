# ADR 0024: Compose-Managed Runtime Stacks

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

Installing Docker Engine and the Compose plugin is necessary, but it still does not define how long-running services should actually be deployed on `docker-runtime-lv3`.

If services are launched ad hoc with `docker run`, the platform will accumulate hidden state:

- no standard filesystem layout for stacks
- no durable boot-time start behavior
- inconsistent restart and health-check policy
- unclear rollback and operator ownership

That is not a good operating contract for a host that is expected to run production workloads.

## Decision

Long-running workloads on `docker-runtime-lv3` will use a compose-managed deployment model.

The deployment contract will be:

1. Runtime stacks are declared with Docker Compose v2.
   - the standard operator interface is `docker compose`
2. Each stack gets a predictable host layout.
   - compose project files live in a versioned path under `/srv/`
   - environment files, bind mounts, and named volumes are declared explicitly
3. Stack lifecycle is host-managed, not shell-session-managed.
   - stacks get a systemd integration path so boot, restart, and failure handling are host-visible
4. Public exposure remains deliberate.
   - container port publication alone does not make a service public
   - public HTTP and HTTPS entry remains mediated by the NGINX edge unless a later ADR says otherwise
5. Each stack must have an operator runbook.
   - deployment, rollback, health verification, and persisted data locations are documented alongside the automation

## Consequences

- Docker runtime services become repeatable and inspectable instead of depending on shell history.
- Compose files, service units, and runbooks can be reviewed separately from host package management.
- Public exposure of runtime services stays aligned with the existing edge model.

## Sources

- <https://docs.docker.com/engine/install/debian/>
