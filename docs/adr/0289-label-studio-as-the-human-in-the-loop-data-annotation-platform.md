# ADR 0289: Label Studio As The Human-In-The-Loop Data Annotation Platform

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Implemented On: not yet
- Date: 2026-03-29

## Context

The platform accumulates LLM interaction traces in Langfuse (ADR 0146), RAG
retrieval results in Qdrant (ADR 0198), and agent session records in
PostgreSQL. This data is a natural source of training and evaluation material,
but there is currently no tool for operators to annotate it systematically.

Annotation work that is done today is ad-hoc:

- Langfuse's human annotation feature supports per-trace thumbs-up/down and
  comments, but not structured multi-field annotation schemas or batch
  labelling workflows
- there is no tool for labelling OCR corrections over Tesseract output
  (ADR 0286), named-entity extraction review, or classification label
  assignment across document corpora

Without structured annotation infrastructure:

- model evaluation remains impressionistic rather than dataset-backed
- fine-tuning data sets cannot be assembled systematically from platform
  traces
- RAG retrieval quality improvements cannot be grounded in labelled
  relevance judgements

Label Studio is a CPU-only, open-source multi-type annotation platform. It
supports text classification, NER, relation extraction, image bounding boxes,
audio transcription review, and custom JSON schemas. It exposes a REST API
for programmatic dataset export and webhook-based annotation events.

## Decision

We will deploy **Label Studio** as the human-in-the-loop data annotation
platform.

### Deployment rules

- Label Studio runs as a Docker Compose service on the docker-runtime VM
- it uses PostgreSQL as its backend database (ADR 0042)
- browser access is enforced at the shared NGINX edge through oauth2-proxy and
  Keycloak (ADR 0063), while app-local admin and API token auth remain the
  Community Edition-compatible automation and break-glass control plane
- the service is published under the platform subdomain model (ADR 0021) at
  `annotate.<domain>`
- secrets are injected from OpenBao following ADR 0077

### Dataset pipeline

- Windmill exports Langfuse trace batches to Label Studio projects via the
  Label Studio REST API on a scheduled basis
- annotators review and label each item; completed annotations are exported
  back to MinIO (ADR 0274) as JSONL datasets via a Windmill post-annotation
  workflow
- exported datasets are versioned in MinIO with a `label-studio/datasets/`
  prefix and tracked in MLflow (ADR 0290) as dataset artifacts

### Annotation schema governance

- annotation schemas (label configurations) are declared in the Ansible role
  defaults as XML templates and applied idempotently on each converge
- schema changes must be version-bumped; existing annotations against an old
  schema are not retroactively re-labelled

### Implementation note

- the first live apply uses the shared edge auth boundary rather than a
  first-class in-app OIDC client because the current Label Studio Community
  Edition path is more stable for repo-managed automation when the browser
  gate and API automation surfaces are separated explicitly

## Consequences

**Positive**

- The platform gains a systematic path from raw LLM traces to structured
  evaluation datasets without leaving the self-hosted environment.
- Label Studio's REST API and webhook support make it a first-class participant
  in Windmill and n8n automation flows rather than a standalone manual tool.
- Multi-annotator support with inter-annotator agreement scoring enables
  dataset quality measurement.
- CPU-only operation means Label Studio can run continuously at negligible cost
  when annotation queues are empty.

**Negative / Trade-offs**

- Label Studio requires operator discipline to maintain annotation queues;
  without regular triage the queue grows stale and annotation coverage drops.
- The current deployment uses two auth surfaces on purpose: shared edge auth
  for browser access and app-local admin or token auth for automation,
  recovery, and deterministic project reconciliation.

## Boundaries

- Label Studio is the structured annotation platform; it does not replace
  Langfuse's per-trace inline comments for quick qualitative feedback.
- Label Studio does not train models; it produces labelled datasets for
  use by MLflow (ADR 0290) and fine-tuning pipelines.
- Label Studio does not store raw audio, video, or large binary assets; those
  remain in MinIO and are referenced by URL in annotation tasks.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0063: Keycloak SSO for internal services
- ADR 0077: Compose secrets injection pattern
- ADR 0146: Langfuse for agent observability
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0290: MLflow as the machine learning experiment tracker and model registry

## References

- <https://labelstud.io/guide/install.html>
