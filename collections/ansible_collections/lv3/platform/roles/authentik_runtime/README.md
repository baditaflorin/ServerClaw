# authentik_runtime

Converges Authentik server, worker, PostgreSQL, Redis, and its OpenBao Agent
sidecar. The role deliberately fails closed when canonical secrets are absent;
an existing deployment must opt into `authentik_secret_bootstrap_mode=adopt_legacy`,
while `generate` is reserved for a confirmed empty installation.

Legacy adoption copies only the four allowlisted Authentik values, verifies the
two PostgreSQL aliases match, preserves a root-only rollback copy, and never
rotates an existing value. The transient runtime environment is deleted before
each OpenBao Agent start and must be freshly rendered with mode `0600` before
application services can start.

After health succeeds, `scripts/reconcile_authentik_oauth.py` applies the
non-secret OAuth manifest and immediately proves a second apply has no changes.
Provider/application IDs and client secrets are preserved during adoption.
