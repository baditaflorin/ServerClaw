# ADR 0288: Flagsmith As The Feature Flag And Remote Configuration Service

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.108
- Implemented In Platform Version: 0.130.71
- Implemented On: 2026-03-30
- Date: 2026-03-29

## Context

Platform services that roll out new behaviour currently do so through one of
two paths: a full redeployment with a changed environment variable, or a
hard-coded boolean that requires a code change and a CI cycle to flip. Neither
path supports:

- enabling a feature for a subset of users or environments without
  redeployment
- rolling back a misbehaving feature in seconds without touching the
  codebase
- reading remote configuration values (e.g. rate-limit thresholds, model
  names, prompt templates) that need to change at runtime

Manually editing environment files and restarting containers to change
a threshold is an awkward GUI and shell session pattern that creates
change-control noise disproportionate to the size of the change.

Flagsmith is a CPU-only, open-source feature flag and remote configuration
service. It exposes a REST API with a full OpenAPI specification for all
management operations (create environment, create flag, set state, set remote
config value) and a lightweight evaluation API that client SDKs call to
retrieve flag state. The evaluation API is designed to be called at application
startup and on every request; the entire flag surface of an environment is
returned in a single API call. There is no GUI step required to flip a flag
or update a configuration value once the SDK is initialised.

## Decision

We will deploy **Flagsmith** as the feature flag and remote configuration
service for platform applications.

### Deployment rules

- Flagsmith runs as a Docker Compose service on the docker-runtime VM using
  the official `flagsmith/flagsmith` image
- Authentication to the Flagsmith management UI and browser-reachable
  management API is enforced at the shared NGINX edge via oauth2-proxy
  and Keycloak (ADR 0063); the verified upstream path does not require a
  service-local OIDC client inside Flagsmith itself
- The service is published under the platform subdomain model (ADR 0021) at
  `flags.<domain>`; the management API is at `flags.<domain>/api/v1/`
- Flagsmith uses the shared PostgreSQL cluster (ADR 0042) with a dedicated
  `flagsmith` database
- Persistent state is included in the backup scope (ADR 0086)
- Secrets (database password, Django secret key, bootstrap admin password,
  and mirrored environment API keys) are injected or mirrored through
  OpenBao following ADR 0077

### API-first operation rules

- Environments, projects, features, and segments are created via the
  Flagsmith management REST API; GUI-only creation is not the canonical
  path and creates untracked state
- The Ansible role for Flagsmith includes a `seed` task that calls the
  management API to create the standard environments (`production`,
  `staging`, `development`) and declare the initial feature set declared
  in `defaults/main.yml`; this is idempotent
- Flag state changes in production are performed via the management API
  from a Windmill flow that requires an operator approval step before
  applying; the approval record is written to the audit log
- Client SDK environment API keys are stored in OpenBao and retrieved by
  services at startup; they are never committed to source or embedded in
  container images

### SDK integration rules

- every platform Python service initialises the Flagsmith Python SDK at
  startup using the environment API key from OpenBao; the SDK is
  configured to poll for flag updates every 60 seconds
- the SDK evaluation call (`get_value`, `is_feature_enabled`) is the only
  permitted mechanism for reading flag state at runtime; environment
  variables may not be used as a shadow flag mechanism
- flag names follow the convention `SCREAMING_SNAKE_CASE`; remote
  configuration keys follow the same convention with a `CONF_` prefix
  (e.g. `CONF_LLM_MODEL_NAME`)

## Consequences

**Positive**

- A misbehaving feature can be disabled in seconds via an API call or
  the management UI without a redeployment cycle.
- Remote configuration values (model names, thresholds, prompt templates)
  are readable at runtime; services adapt without restart.
- The seed task ensures all environments and baseline flags are
  version-controlled and reproducible after a fresh deploy.
- The single evaluation API call retrieves all flags for an environment;
  there is no per-flag network round trip at request time.

**Negative / Trade-offs**

- The Flagsmith SDK introduces a soft dependency at service startup; if
  Flagsmith is unavailable, the SDK falls back to default values, but
  operators must ensure defaults are safe rather than disabling features
  that must be on by default.
- Flag proliferation is a risk; flags that are never cleaned up accumulate
  and make the flag list unreadable. A quarterly flag audit is required.

## Boundaries

- Flagsmith manages feature flags and remote configuration values; it does
  not replace environment variables for secrets or for values that must be
  available before the SDK initialises.
- Flagsmith is not an A/B testing platform for end users; it is used for
  operator-controlled feature rollouts and runtime configuration.
- Flagsmith flag state is not used as an authorisation mechanism; access
  control remains in Keycloak and the platform API gateway.
- Analytics on flag evaluation counts are available in Flagsmith's built-in
  reporting; this does not replace Plausible (ADR 0283) for web traffic
  analytics.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services

## References

- <https://docs.flagsmith.com/deployment/hosting/self-hosted>
- <https://docs.flagsmith.com/clients/rest>
