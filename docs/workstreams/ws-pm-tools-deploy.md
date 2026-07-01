# Workstream: 10 Project Management Tools

## Scope

Deploy ten project-management tools behind the shared Nginx edge:
Focalboard, Huly, Kan, Leantime, OpenProject, Planka, Taiga, Tiki, Vikunja, and
FlowInquiry.

## Current Live State

As of 2026-07-01, four services are reachable from the workstation through the
public edge:

- `planka.0mcp.com`: HTTP 200
- `focalboard.0mcp.com`: HTTP 200
- `kan.0mcp.com`: HTTP 307 redirect to `/login`
- `huly.0mcp.com`: HTTP 200

The remaining six public routes exist in Nginx, but their runtime listeners
are not present on `docker-runtime-lv3`:

- `leantime.0mcp.com`: no `/opt/leantime` runtime stack, port `8114` closed.
- `openproject.0mcp.com`: no `/opt/openproject` runtime stack, port `8115`
  closed.
- `taiga.0mcp.com`: no `/opt/taiga` runtime stack, port `8117` closed.
- `tiki.0mcp.com`: no `/opt/tiki` runtime stack, port `8118` closed.
- `vikunja.0mcp.com`: no `/opt/vikunja` runtime stack, port `3456` closed.
- `flowinquiry.0mcp.com`: no `/opt/flowinquiry` runtime stack, port `8119`
  closed.

## 2026-07-01 Edge Reachability Fix

Focalboard, Kan, and Planka initially passed direct checks on
`docker-runtime-lv3` but timed out from the workstation. Root cause: their
compose files published ports only on `127.0.0.1`, while `nginx-lv3` proxies to
the Docker runtime VM address `10.10.10.20`.

Live fix applied:

- `/opt/focalboard/docker-compose.yml`: `0.0.0.0:8111:8000`
- `/opt/kan/docker-compose.yml`: `0.0.0.0:8113:3000`
- `/opt/planka/docker-compose.yml`: `0.0.0.0:8116:1337`
- Recreated only those three compose services with `docker compose up -d`.

Template fix committed in this workstream:

- `collections/ansible_collections/lv3/platform/roles/focalboard_runtime/templates/docker-compose.yml.j2`
- `collections/ansible_collections/lv3/platform/roles/kan_runtime/templates/docker-compose.yml.j2`
- `collections/ansible_collections/lv3/platform/roles/planka_runtime/templates/docker-compose.yml.j2`

Verification:

- Workstation `curl https://planka.0mcp.com/`: HTTP 200
- Workstation `curl https://focalboard.0mcp.com/`: HTTP 200
- Workstation `curl https://kan.0mcp.com/`: HTTP 307 redirect to `/login`
- `docker-runtime-lv3` containers publish `0.0.0.0:8111`, `0.0.0.0:8113`, and
  `0.0.0.0:8116`.

## 2026-07-01 Huly Full-Stack Install

Huly initially had `/opt/huly/docker-compose.yml` rendered for a front-only
placeholder, but there were no usable Huly containers and port `8112` was
closed. Starting that placeholder pulled `hardcoreeng/front:latest`, but the
container crashed with `Please provide server secret`.

Root cause: the `hardcoreeng/front` image is not a standalone Huly deployment.
It expects the official self-host environment, including shared application
secret and backend services.

Live fix applied:

- Replaced `/opt/huly/docker-compose.yml` with a full Huly stack based on the
  upstream `huly-selfhost` compose topology.
- Added `/opt/huly/.env` with generated Huly, CockroachDB, and Redpanda secrets
  stored persistently under `/etc/lv3/huly/`.
- Added `/opt/huly/.huly.nginx` as the internal Huly nginx router.
- Removed the orphaned `huly-front` placeholder container via
  `docker compose up -d --force-recreate --remove-orphans`.
- Published the internal Huly nginx on `0.0.0.0:8112` for the existing edge
  proxy route.
- Corrected the Redpanda healthcheck to use `rpk cluster info` without SASL
  flags, matching the stack's non-SASL internal listener.

Template fix committed in this workstream:

- `collections/ansible_collections/lv3/platform/roles/huly_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/huly_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/huly_runtime/templates/docker-compose.yml.j2`
- `collections/ansible_collections/lv3/platform/roles/huly_runtime/templates/huly.env.j2`
- `collections/ansible_collections/lv3/platform/roles/huly_runtime/templates/huly.nginx.conf.j2`

Verification:

- `docker-runtime-lv3` publishes `0.0.0.0:8112`.
- Huly `minio`, `elastic`, and `redpanda` healthchecks are healthy.
- `nginx-lv3` can connect to `10.10.10.20:8112`.
- Workstation `curl https://huly.0mcp.com/`: HTTP 200.
