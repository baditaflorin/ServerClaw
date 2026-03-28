# dify_postgres

## Purpose

Provision the named PostgreSQL role and database used by the repo-managed Dify runtime.

## Use Case

Run as part of `playbooks/dify.yml` before the runtime converges on `docker-runtime-lv3`.

## Inputs

- `dify_database_name`
- `dify_database_user`
- `dify_database_password_local_file`

## Outputs

- PostgreSQL role `dify`
- PostgreSQL database `dify`
- controller-local mirrored password artifact for the runtime

## Idempotency

Fully idempotent.

## Dependencies

- ADR 0197
- `lv3.platform.postgres_vm`
