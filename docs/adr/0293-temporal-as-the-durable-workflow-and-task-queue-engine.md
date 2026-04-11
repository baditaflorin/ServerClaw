# ADR 0293: Temporal As The Durable Workflow And Task Queue Engine

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.177.109
- Implemented In Platform Version: 0.130.72
- Implemented On: 2026-03-30
- Date: 2026-03-29

## Context

The platform runs multi-step, long-running operations that today are
implemented as a combination of Windmill flows, shell scripts, and Ansible
playbooks:

- document ingestion pipelines (fetch → extract via Tika → embed via
  Ollama → upsert into Qdrant) where each step can take minutes and any
  step may fail and need to retry independently
- VM provisioning sequences (Netbox IP allocation → Proxmox VM creation →
  Ansible bootstrap → health check) where partial completion leaves
  infrastructure in an inconsistent state
- scheduled data synchronisation jobs that must run to completion exactly
  once even if the worker crashes mid-execution

Windmill covers the orchestration of short-to-medium flows well, but it
does not provide durable execution guarantees: if a Windmill worker
restarts mid-flow, the flow must be re-triggered from the beginning, and
there is no built-in mechanism for checkpointing intermediate state or
replaying completed steps from where they left off.

Temporal is a CPU-only, open-source durable workflow engine. Workflows are
written as ordinary code (Python, Go, Java, TypeScript) decorated with
Temporal SDK annotations. The Temporal server persists the workflow event
history in PostgreSQL; if a worker crashes, the workflow resumes from the
last successfully completed activity on any available worker without
re-executing completed steps. All workflow management operations—starting a
workflow, querying its state, cancelling it, listing running executions, and
managing schedules—are available via the Temporal gRPC API and its
equivalent HTTP frontend API, with no GUI step required.

## Decision

We will deploy **Temporal** as the durable workflow engine for long-running,
multi-step operations where at-least-once activity execution and crash
recovery are required.

### Deployment rules

- Temporal server runs as a Docker Compose stack (frontend, history, matching,
  and worker services, plus the `temporal-ui-server` for diagnostic access)
  on the docker-runtime VM using the official `temporalio/server` and
  `temporalio/ui` images
- The Temporal server is internal-only; no public subdomain is issued
- The gRPC API endpoint is `temporal-frontend:7233` on the internal Compose
  network; the HTTP frontend API is `temporal-frontend:7243`
- Operator diagnostics stay loopback-only on `docker-runtime`
  (`127.0.0.1:7233`, `127.0.0.1:7243`, and `127.0.0.1:8099`) and are consumed
  through the documented Proxmox jump-path tunnel instead of public edge
  publication
- Temporal uses the shared PostgreSQL cluster (ADR 0042) with a dedicated
  `temporal` database and a `temporal_visibility` database for the
  visibility store
- All workflow history is stored in PostgreSQL and included in the backup
  scope (ADR 0086)
- Secrets (database credentials, inter-service mTLS certificates) are
  injected from OpenBao following ADR 0077

### API-first operation rules

- Workflows are started exclusively via the Temporal SDK or the HTTP API
  (`POST /api/v1/namespaces/{namespace}/workflows`); there are no GUI-
  triggered workflow starts in production
- Workflow schedules (recurring executions) are created and managed via the
  Temporal Schedules API; Windmill cron is used only for workflows that are
  short enough to run without durable guarantees
- Workflow and activity definitions are version-controlled in the `workflows/`
  directory of the relevant service repository; the worker binary is built
  and deployed by Woodpecker CI (ADR 0287)
- The Temporal Workflow Query API is used by Windmill monitoring flows to
  retrieve the current state of long-running operations (e.g. "is the
  nightly document ingestion still running?") without reading PostgreSQL
  directly
- Namespace management (creating namespaces for different domains) is
  performed via the Temporal `temporal` CLI or the namespaces REST API during
  Ansible provisioning; namespaces are declared in `defaults/main.yml` and
  applied idempotently

### Workflow design rules

- each activity function performs exactly one side-effectful operation and
  is idempotent; the activity is the unit of retry, not the workflow
- retry policy for activities is declared in code via `ActivityOptions`;
  the platform default is 5 retries with exponential backoff capped at
  5 minutes
- workflow input and output are serialised as JSON-compatible dataclasses;
  Protobuf is used for cross-language workflows
- workflows that interact with the Temporal HTTP API from within a Windmill
  flow use the API token stored in OpenBao; they do not use the internal
  gRPC endpoint directly

## Consequences

**Positive**

- A multi-hour document ingestion pipeline that crashes at step 7 of 10
  resumes from step 8 on the next available worker; the user does not
  need to re-submit the job or track which documents were already processed.
- Workflow state (current activity, retry count, input/output of completed
  steps) is queryable via the Temporal API; operators can inspect in-flight
  operations without querying PostgreSQL or reading log files.
- The decoupling of workflow definition (code in the repository) from
  execution infrastructure (Temporal server) means workflow logic can be
  tested locally using the Temporal Go/Python test framework without a
  running Temporal server.
- Temporal Schedules replace ad-hoc cron entries for workflows that require
  durable execution guarantees; schedule definitions are version-controlled
  and managed via API.

**Negative / Trade-offs**

- Temporal's multi-service architecture (frontend, history, matching, worker)
  has a higher baseline memory footprint (~500 MB total) than a single-binary
  service; the docker-runtime VM must have headroom.
- Workflow code must be instrumented with Temporal SDK annotations; existing
  scripts cannot be made durable without being rewritten as Temporal workflows
  and activities.
- The PostgreSQL event history grows proportionally to workflow volume; a
  retention policy must be configured to prune completed workflow histories
  older than the compliance retention window.

## Boundaries

- Temporal handles durable, long-running workflows where crash recovery and
  at-least-once activity execution are required; Windmill (ADR 0238) handles
  shorter operational flows, UI-triggered scripts, and data transformations
  that do not require durability guarantees.
- Temporal is not a message broker; event distribution between services
  remains the responsibility of NATS JetStream (ADR 0276) and Redpanda
  (ADR 0290).
- The Temporal UI (served by `temporal-ui-server`) is available at an
  internal port for diagnostic workflow inspection; it is not published
  publicly and is not the primary interface for operational queries.
- Temporal does not replace the platform's scheduler for simple cron jobs
  that do not require durability; those remain as Windmill scheduled flows.

## Related ADRs

- ADR 0042: PostgreSQL as the shared relational database
- ADR 0077: Compose secrets injection pattern
- ADR 0086: Backup and recovery for stateful services
- ADR 0145: Ollama for local LLM inference
- ADR 0238: Windmill as the operational workflow and script automation layer
- ADR 0276: NATS JetStream as the platform event bus
- ADR 0285: Qdrant as the vector database for the RAG pipeline
- ADR 0287: Woodpecker CI as the API-driven continuous integration server
- ADR 0290: Redpanda as the Kafka-compatible streaming platform

## References

- <https://docs.temporal.io/references/api>
- <https://docs.temporal.io/develop/python>
