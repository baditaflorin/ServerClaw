# ADR 0291: JupyterHub As The Interactive Notebook Environment

- Status: Deprecated (see service removal ADR — service removed from platform)
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.111
- Implemented In Platform Version: 0.130.71
- Implemented On: 2026-03-30
- Date: 2026-03-29

## Context

The platform has strong production-automation tools (Windmill, n8n, Temporal)
but no environment for *exploratory* data work: ad-hoc data queries, prototype
agent chains, dataset quality checks, or one-off analysis of PostgreSQL,
InfluxDB, or Loki data before that logic is promoted to a production workflow.

The gap is most visible in these scenarios:

- an operator wants to understand the shape of a Langfuse dataset before
  configuring a Label Studio annotation schema (ADR 0289)
- a developer wants to prototype a new RAG retrieval strategy against live
  Qdrant data before committing it to a Windmill workflow
- a fine-tuning engineer wants to validate that a Label Studio export has the
  expected class balance before launching an MLflow experiment (ADR 0290)
- post-incident analysis requires ad-hoc Loki log querying and statistical
  summarisation beyond what Grafana supports

Windmill supports Python scripts but its editor is optimised for production
automation with structured inputs, not for free-form exploration with rich
inline output. JupyterHub is the industry standard for multi-user interactive
notebooks. It runs CPU-only and supports Python, with optional kernels for
other languages.

## Decision

We will deploy **JupyterHub** as the shared interactive notebook environment.

### Deployment rules

- JupyterHub runs as a Docker Compose service on the docker-runtime VM
- authentication is delegated to Keycloak via OIDC (ADR 0063)
- each user receives an isolated single-user Jupyter server spawned from a
  common base Docker image defined in the Ansible role
- notebook files are stored on per-user named volumes; shared notebooks are
  stored in a `jupyterhub-shared` MinIO bucket (ADR 0274)
- the service is published under the platform subdomain model (ADR 0021) at
  `notebooks.<domain>`
- secrets for platform data sources (PostgreSQL, InfluxDB, MinIO, Qdrant,
  LiteLLM) are available as environment variables inside each user server,
  injected from OpenBao at spawn time following ADR 0077

### Kernel and library conventions

- the base kernel image includes: pandas, sqlalchemy, psycopg2, influxdb-client,
  qdrant-client, openai (pointed at LiteLLM), minio, and langfuse Python SDK
- additional libraries may be installed inside a user session with `%pip install`
  but are not persisted between sessions unless added to the base image in the
  Ansible role
- the base image does not include GPU-accelerated ML libraries; CPU-only torch
  and transformers are available for prototyping

### Promotion path

- code prototyped in a notebook that passes validation is promoted to a
  Windmill script or n8n workflow by the operator; notebooks are not run in
  production directly
- notebooks committed to the `jupyterhub-shared` MinIO bucket are treated as
  living documentation and may be referenced from Outline (ADR 0199)

## Consequences

**Positive**

- Exploratory data work has a sanctioned, reproducible environment with access
  to all platform data sources under the same OIDC identity.
- Notebook isolation per user prevents one user's environment from affecting
  another's while still sharing the same base image and data source credentials.
- The direct connection to LiteLLM (ADR 0287) and Qdrant means agent-chain
  prototypes can query live data, making explorations immediately applicable.
- CPU-only kernels mean JupyterHub can run on the existing VM without GPU
  scheduling contention.

**Negative / Trade-offs**

- Per-user single-server spawning means each active session consumes
  approximately 200–400 MB of RAM; concurrent active users must be bounded
  by the VM's memory headroom.
- Notebooks that access production data sources must be governed carefully;
  a runaway loop or large query can impact production services sharing the
  same PostgreSQL or Qdrant instance.

## Boundaries

- JupyterHub is an exploratory and prototyping environment; production
  scheduled jobs and automation remain in Windmill and n8n.
- JupyterHub notebooks are not the authoritative home for platform code;
  production code lives in the Gitea repository.
- JupyterHub does not replace Grist (ADR 0279) for structured operational
  data management; Grist is for non-programmer operators, JupyterHub is
  for technical staff who write code.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0199: Outline as the living knowledge wiki
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0287: LiteLLM as the unified LLM API proxy and router
- ADR 0289: Label Studio as the human-in-the-loop data annotation platform
- ADR 0290: MLflow as the machine learning experiment tracker and model registry

## References

- <https://jupyterhub.readthedocs.io/en/stable/>
