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

After health succeeds, the role first reconciles repository-owned OAuth scope
mappings, then `scripts/reconcile_authentik_oauth.py` applies the non-secret
provider/application manifest and immediately proves both passes have no
changes. Provider/application IDs and client secrets are preserved during
adoption. The Grafana-only groups scope exposes only its two Grafana role
groups; it does not add those claims to other OAuth clients.

The role also mounts a managed recovery-flow blueprint and renders Authentik's
global SMTP settings through the existing OpenBao runtime payload. Transactional
mail uses the private `mail-gateway-smtp:1588` bridge and its provider-backed
delivery path, with the configured gateway sender. Recovery links are
short-lived and rate-limited; the SMTP password remains outside the repository
and the flow blueprint.
