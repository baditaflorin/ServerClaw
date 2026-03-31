# ADR 0287: Woodpecker CI As The API-Driven Continuous Integration Server

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.110
- Implemented In Platform Version: 0.130.73
- Implemented On: 2026-03-30
- Date: 2026-03-29

## Context

The platform runs CI pipelines for Ansible roles, container image builds, and
ADR validation scripts. At present these are either triggered manually or rely
on cron-scheduled Windmill flows. There is no event-driven CI server that:

- fires a pipeline automatically when code is pushed to Gitea
- provides a queryable API for pipeline status, log retrieval, and secret
  management
- allows pipelines to be defined as YAML files version-controlled alongside
  the code they test

The absence of a CI server means pipeline definitions are scattered across
Windmill flows and Ansible playbooks. Triggering a build or checking its
status requires opening a GUI. Secrets used in pipelines are duplicated
across Windmill and Ansible rather than managed in one place.

Woodpecker CI is a CPU-only, open-source CI server forked from Drone CI.
It exposes a complete REST API—pipeline execution, step log streaming, secret
CRUD, repository registration, and agent management are all available as
documented HTTP endpoints with a published OpenAPI specification. Pipelines
are defined in `.woodpecker.yml` files in the repository root. The web UI
is fully optional; every operation the UI performs is also available via the
`woodpecker-cli` tool or direct API call.

## Decision

We will deploy **Woodpecker CI** as the platform's event-driven continuous
integration server.

### Deployment rules

- Woodpecker server and one Woodpecker agent run as Docker Compose services
  on the docker-runtime VM
- Authentication is delegated to Gitea OAuth2 (which in turn delegates to
  Keycloak, ADR 0063); no local Woodpecker accounts are created
- The server is published under the platform subdomain model (ADR 0021) at
  `ci.<domain>`; the API is at `ci.<domain>/api/`
- Woodpecker uses the shared PostgreSQL cluster (ADR 0042) with a dedicated
  `woodpecker` database
- All persistent state (pipeline history, secrets, repository registrations)
  is stored in PostgreSQL and included in the backup scope (ADR 0086)
- Secrets (database password, Gitea OAuth client credentials, agent secret)
  are injected from OpenBao following ADR 0077

### API-first operation rules

- Repository activation and deactivation are performed via the Woodpecker
  REST API (`POST /api/repos/{owner}/{name}`) from Windmill provisioning
  workflows; clicking "activate" in the browser UI is not the canonical
  path for new repositories
- Pipeline secrets are created and rotated via the Woodpecker secrets API
  (`POST /api/repos/{owner}/{name}/secrets`); the source of record for secret
  values is OpenBao, and a Windmill sync flow writes them to Woodpecker on
  any rotation
- Pipeline status is queried via the builds API
  (`GET /api/repos/{owner}/{name}/builds`) from Windmill approval gates;
  a deployment workflow waits for a green build before promoting an image
- Agent registration uses the agent token API; additional agents are
  registered programmatically without manual GUI steps

### Pipeline definition rules

- all pipelines are defined in `.woodpecker.yml` at the repository root;
  pipeline logic that cannot be expressed in YAML is extracted into scripts
  in a `ci/` directory within the repo
- pipelines must not embed secrets as literals; they reference named
  Woodpecker secrets injected as environment variables
- the Ansible role that deploys Woodpecker includes a `seed_repos` task that
  calls the Woodpecker API to register repositories declared in
  `defaults/main.yml`; this is idempotent and removes the need to manually
  activate repos after a fresh deploy

## Consequences

**Positive**

- Code pushes to Gitea fire pipelines automatically via webhooks; no manual
  trigger is needed.
- Pipeline status, logs, and secrets are all queryable via REST API, allowing
  Windmill deployment gates to block on CI results without browser interaction.
- Pipeline definitions live in the repository alongside the code; a PR diff
  shows both code changes and the corresponding CI changes.
- Woodpecker's agent model allows workload isolation; a future GPU or
  high-memory agent can be added and targeted by specific pipelines without
  changing the server configuration.

**Negative / Trade-offs**

- Woodpecker requires Gitea OAuth2 to be configured; if Gitea is unavailable,
  Woodpecker login is also unavailable. The API token (separate from OAuth)
  must be pre-generated and stored in OpenBao for break-glass access.
- Woodpecker does not support matrix builds natively at the same level as
  GitHub Actions; complex matrix scenarios must be modelled as multiple
  pipeline steps or separate workflow files.

## Boundaries

- Woodpecker runs CI pipelines for code validation, image builds, and
  integration tests; it does not replace Windmill for long-running
  operational automation or scheduled data workflows.
- Woodpecker is not the deployment executor; it produces artefacts and
  reports a pass/fail signal. Deployment is performed by Windmill flows
  or Ansible, which query the Woodpecker API for the green-build gate.
- Production secret injection into deployed services is done by OpenBao
  directly; Woodpecker secrets are CI-only and are not a general secret
  distribution mechanism.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services

## References

- <https://woodpecker-ci.org/docs/usage/api>
- <https://woodpecker-ci.org/api>
