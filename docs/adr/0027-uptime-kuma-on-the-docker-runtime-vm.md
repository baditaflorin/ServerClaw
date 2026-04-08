# ADR 0027: Uptime Kuma On The Docker Runtime VM

- Status: Accepted
- Implementation Status: Accepted
- Implemented In Repo Version: N/A
- Implemented In Platform Version: 0.19.0
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

The platform already has internal metrics and dashboards through ADR 0011, but it still lacked a simple service-level uptime view and a low-friction way to add endpoint checks as operational work continues.

The dedicated Docker runtime VM at `10.10.10.20` is intentionally the place for long-running containerized application workloads.

ADR 0021 already established the NGINX VM at `10.10.10.10` as the single public HTTP and HTTPS edge for published services, and ADR 0015 established the stable `lv3.org` hostname model.

That left a clear gap:

1. deploy a lightweight uptime application on the Docker runtime VM
2. publish it at a named subdomain through the NGINX edge
3. keep the DNS publication and NGINX publication in version-controlled automation
4. preserve a durable operator/tooling path for adding or updating monitors without relying on undocumented browser-only state

## Decision

We run Uptime Kuma on the Docker runtime VM under `/opt/uptime-kuma`.

Deployment model:

- runtime: Docker on `docker-runtime-lv3`
- application path: `/opt/uptime-kuma`
- persistent data path: `/opt/uptime-kuma/data`
- image source: official `louislam/uptime-kuma` container image

Publication model:

- public hostname: `uptime.lv3.org`
- DNS management: Hetzner DNS API, automated from the control machine
- public edge: reverse proxy through the NGINX VM alongside the existing published hostnames
- TLS: included in the shared edge certificate managed on the NGINX VM

Operator/tooling model:

- Uptime Kuma initial bootstrap remains auth-enabled
- the control machine stores the durable local session material outside git under `.local/uptime-kuma/`
- repo automation uses that stored local auth plus the internal Socket.IO management flow to add and update monitors
- monitor definitions live in version-controlled seed data so the initial managed set is reproducible

## Consequences

- The platform gets a dedicated uptime dashboard without exposing the Docker runtime VM directly to the public internet.
- Future monitor additions can be driven from repo automation instead of ad hoc browser clicks.
- The NGINX edge automation must handle certificate expansion when new published hostnames are added, not only first issuance.
- Uptime Kuma becomes another stateful service on the Docker runtime VM and should be treated as backed-up operational infrastructure in later policy work.

## Follow-up requirements

- If alert routing is needed beyond the UI defaults, define it in a follow-up workstream instead of embedding notification provider secrets ad hoc.
- If additional runtime applications are published from the Docker VM, they should follow the same DNS-plus-edge publication model rather than bypassing the NGINX edge.
- If Uptime Kuma user or token rotation happens, update the local secret material and rerun the documented bootstrap flow in the runbook.
