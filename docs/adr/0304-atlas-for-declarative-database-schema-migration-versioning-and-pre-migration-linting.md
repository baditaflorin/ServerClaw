# ADR 0304: Atlas For Declarative Database Schema Migration Versioning And Pre-Migration Linting

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.144
- Implemented In Platform Version: 0.130.90
- Implemented On: 2026-04-02
- Date: 2026-03-29

## Context

PostgreSQL is the shared database for 15+ platform services. Each service manages
its own schema migrations through its own mechanism:

- Keycloak runs Liquibase migrations at startup
- Gitea runs Go `gorm` automigrations at startup
- Windmill bundles its own migration runner
- Langfuse, Plane, and NetBox each have their own migration tools

This arrangement has several operational risk profiles:

- **No pre-flight lint**: no tool verifies that an upcoming migration is safe
  before it runs; a destructive `DROP COLUMN` or `ALTER TABLE` that locks rows
  can be detected only after it begins executing against production data
- **No ordered record**: there is no single source of truth for the schema version
  of each database; the platform cannot answer "what was the schema state of the
  `windmill` database at a specific timestamp" without reconstructing it from
  application code history
- **No drift detection**: the schema actually present in the production database
  can silently diverge from the schema the application expects after a failed or
  partial migration; the platform has no automated check for this

Atlas (`ariga-io/atlas`) is a database schema management tool that provides
versioned migration files, a schema linter, a drift detection command, and a
declarative schema diffing engine. It is Apache-2.0-licensed, written in Go,
ships as a single binary and a Docker image, and has been in production use since
2021. Atlas exposes a REST API server mode and a JSON output mode for all
commands, making it suitable for programmatic integration with the CI gate and
Windmill workflows.

## Decision

We will integrate **Atlas** as the migration linting and drift detection layer
for platform-managed PostgreSQL databases. Atlas does not replace each service's
own migration runner; it provides a pre-flight lint gate and a post-deploy schema
assertion check.

### Deployment rules

- Atlas runs as a Docker Compose `run` step in the Gitea Actions CI gate (ADR 0087)
  and as a scheduled Windmill job (`atlas-drift-check`) for post-deploy
  verification
- the Atlas Docker image is pulled through Harbor (ADR 0068) and pinned to a SHA
  digest; the version is tracked in `versions/stack.yaml`
- Atlas database credentials are injected from OpenBao (ADR 0077) at runtime;
  no credentials are stored in the repository or in environment variables at
  rest
- Atlas runs in read-only mode against the production database for drift
  detection; it does not execute migrations; each service's own migration runner
  remains authoritative for execution

### Schema version registry

- for each platform-managed database, a schema snapshot file is maintained at
  `config/atlas/<service>.hcl` in Atlas HCL format
- on every successful service deployment, the post-verify step runs
  `atlas schema inspect --format hcl` and overwrites the corresponding `.hcl`
  file; if the result differs from the committed baseline, a pull request is
  automatically opened by the Windmill post-deploy job to update the snapshot
- the `.hcl` files are version-controlled; `git log` on any schema file provides
  a timestamped history of every schema change

### Pre-migration lint gate

- for services that bundle migration SQL files under `migrations/<service>/`
  in the repository, Atlas lint is run as a CI gate step:
  `atlas migrate lint --dev-url <dev-db> --dir file://migrations/<service>`
- Atlas lint detects: missing `IF NOT EXISTS` clauses, `ALTER TABLE ... ADD NOT NULL`
  without a default (which locks all rows on PostgreSQL <12), `DROP TABLE` and
  `DROP COLUMN` without a corresponding rollback stub, and schema modifications
  that change constraint names referenced by application code
- any lint error at `ERROR` level is a blocking CI gate failure; `WARNING`-level
  findings produce a PR annotation

### Drift detection rules

- the scheduled `atlas-drift-check` Windmill job runs daily and compares the live
  database schema against the committed `.hcl` snapshot for each service
- a schema drift finding is emitted as a structured JSON record at
  `receipts/atlas-drift/<service>-<date>.json`
- if drift is detected, a NATS `platform.db.schema_drift` event is published
  (ADR 0276) and an ntfy `platform.db.warn` notification is sent (ADR 0299)
- drift between the production database and the replica is checked separately;
  a replica schema divergence is always a `CRITICAL` event

## Consequences

**Positive**

- destructive or row-locking migrations are caught by lint before they reach the
  production database; this directly reduces the risk of accidental data loss or
  service outage during a schema change
- the committed `.hcl` schema snapshots give the platform a forensic record of
  every database schema state over time without reconstructing it from application
  code history
- drift detection surfaces silent schema divergences introduced by service
  automigration bugs or manual schema edits before they cause application errors

**Negative / Trade-offs**

- Atlas lint coverage is limited to migration SQL files committed to the repo;
  services that run automigrations at startup (Keycloak, Gitea) cannot have their
  migrations linted before execution without migrating to a versioned migration
  file model, which is a separate project
- the `dev-url` for lint requires a throwaway PostgreSQL instance on the build
  host; the CI gate must provision and tear down this instance per lint run
- Atlas schema HCL uses its own dialect; mapping the live PostgreSQL schema to
  HCL is reliable for common DDL but may produce imprecise representations for
  advanced PostgreSQL features (partitioned tables, custom types)

## Boundaries

- Atlas lints and detects drift; it does not execute migrations; each service's
  own migration runner remains the execution authority
- Atlas covers the PostgreSQL instance on `postgres-lv3`; it does not cover
  InfluxDB, Redis, or other non-relational data stores
- Atlas does not replace pgaudit (ADR 0303) for query audit; pgaudit captures
  runtime DDL events while Atlas captures intent-to-migrate at design time

## Related ADRs

- ADR 0042: Step-CA (PostgreSQL VM is ADR 0026)
- ADR 0066: Structured mutation audit log
- ADR 0077: Compose runtime secrets injection
- ADR 0080: Maintenance window and change suppression protocol
- ADR 0087: Repository validation gate
- ADR 0271: Backup coverage assertion ledger
- ADR 0276: NATS JetStream as the platform event bus
- ADR 0297: Renovate Bot as the automated stack version upgrade proposer
- ADR 0299: Ntfy as the push notification channel
- ADR 0303: pgaudit for PostgreSQL query audit logging

## References

- <https://github.com/ariga/atlas>
