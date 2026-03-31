# ADR 0290: MLflow As The Machine Learning Experiment Tracker And Model Registry

- Status: Accepted
- Implementation Status: Not Implemented
- Implemented In Repo Version: N/A
- Implemented In Platform Version: N/A
- Date: 2026-03-29

## Context

The platform runs LLM inference via Ollama (ADR 0145), traces LLM interactions
in Langfuse (ADR 0146), and produces annotated datasets via Label Studio
(ADR 0289). As the platform moves toward autonomous operation, it will need to:

- fine-tune or adapt smaller open-source models on domain-specific data
- evaluate multiple model variants against the same benchmark dataset
- promote a validated model version from experiment to the Ollama model
  registry in a controlled, auditable way
- reproduce any model variant given its training run parameters and dataset
  version

Langfuse covers LLM observability and evaluation traces for deployed models.
It does not cover the experiment lifecycle: parameter sweeps, metric
comparison across runs, dataset lineage, and model artefact versioning for
candidate models that are not yet deployed.

MLflow is a CPU-only, open-source experiment tracking and model registry
platform. It records parameters, metrics, and artefacts for each training run,
supports dataset versioning, and provides a model registry with staging and
production transitions. It runs as a Python server with PostgreSQL as its
backend store and MinIO as its artefact store.

## Decision

We will deploy **MLflow** as the machine learning experiment tracker and model
registry for platform model development.

### Deployment rules

- MLflow runs as a Docker Compose service on the docker-runtime VM
- it uses PostgreSQL as its backend store (ADR 0042) and MinIO (ADR 0274)
  as its artefact store (`mlflow-artifacts` bucket)
- authentication is provided by the NGINX edge with OAuth2-Proxy (the
  MLflow server itself has basic auth; OIDC delegation is handled at the
  reverse proxy layer)
- the service is published under the platform subdomain model (ADR 0021) at
  `mlflow.<domain>`
- secrets are injected from OpenBao following ADR 0077

### Experiment governance

- every fine-tuning or adaptation run must be logged as an MLflow experiment
  with at minimum: base model name, dataset version, hyperparameters, and
  evaluation metrics
- dataset artefacts are stored in MinIO under `label-studio/datasets/` and
  referenced in MLflow runs by URI; dataset content is not duplicated into
  MLflow artefact storage
- model artefacts (GGUF adapters, LoRA weights) are stored in the
  `mlflow-artifacts` MinIO bucket

### Model promotion path

- candidate models enter the MLflow model registry in `Staging` state
- promotion to `Production` requires a documented evaluation run logged in
  MLflow showing metric improvement over the current baseline
- promotion from MLflow `Production` to Ollama (ADR 0145) is a manual step
  performed by a Windmill workflow that downloads the artefact and runs the
  Ollama model import command

## Consequences

**Positive**

- Fine-tuning and adaptation work becomes reproducible and comparable; no
  run is unrecorded.
- The model promotion path creates a clear gate between experiment and
  production that prevents untested models from entering the inference stack.
- MLflow's built-in UI allows side-by-side metric comparison across runs
  without custom dashboarding.
- CPU-only tracking server with MinIO artefact storage costs nothing when
  no experiments are running.

**Negative / Trade-offs**

- MLflow tracking client code must be added to every training script; runs
  that do not call the tracking API produce no record.
- The MLflow model registry uses its own staging/production concept which
  must be kept synchronised with the actual Ollama model state; they are not
  automatically linked.

## Boundaries

- MLflow tracks model development experiments and manages candidate model
  artefacts; it does not replace Langfuse for deployed model observability.
- MLflow does not run training compute; training jobs run in Windmill or
  standalone scripts that call the MLflow tracking API.
- MLflow does not serve models; serving remains Ollama's responsibility.
- MLflow's model registry covers only platform-developed model adaptations;
  base models downloaded directly from Ollama Hub are not registered in
  MLflow unless they are the baseline for an experiment.

## Related ADRs

- ADR 0021: Public subdomain publication at the NGINX edge
- ADR 0042: PostgreSQL as the shared relational database
- ADR 0077: Compose secrets injection pattern
- ADR 0145: Ollama for local LLM inference
- ADR 0146: Langfuse for agent observability
- ADR 0274: MinIO as the S3-compatible object storage layer
- ADR 0289: Label Studio as the human-in-the-loop data annotation platform

## References

- <https://mlflow.org/docs/latest/tracking.html>
