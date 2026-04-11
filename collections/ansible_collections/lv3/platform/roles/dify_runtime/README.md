# dify_runtime

## Purpose

Converge the repo-managed Dify runtime stack, bootstrap secrets, and verification hooks on `docker-runtime`.

## Use Case

Run from `playbooks/dify.yml` during ADR 0197 live apply or replay.

## Inputs

- runtime topology and public URL data
- PostgreSQL password mirrored locally by `dify_postgres`
- controller-local Dify and gateway bootstrap artifacts

## Outputs

- Dify API, worker, web, reverse proxy, Redis, Qdrant, sandbox, plugin daemon, and SSRF proxy containers
- bootstrap admin credentials mirrored under `.local/dify/`
- exported smoke workflow under `platform/dify-workflows/`

## Idempotency

Fully idempotent after bootstrap artifacts exist.

## Dependencies

- ADR 0197
- `lv3.platform.docker_runtime`
- `lv3.platform.linux_guest_firewall`
- `lv3.platform.common` openbao compose env helper
