# mattermost_postgres

Creates the PostgreSQL database, roles, and mirrored controller-local password artifact for Mattermost.

Inputs: `mattermost_database_*`, `mattermost_postgres_*`, `mattermost_local_artifact_dir`.
Outputs: managed PostgreSQL roles and database on `postgres`, plus `.local/mattermost/database-password.txt`.
