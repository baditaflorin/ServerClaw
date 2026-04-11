# rag_context_runtime

Deploys the private platform context API, its Qdrant-backed retrieval index,
and the ADR 0263 ServerClaw memory substrate on `docker-runtime`.

Inputs: Docker compose paths, Qdrant image, shared PostgreSQL DSN, local
embedding backend settings, controller-local API token path, and repo corpus
source paths.
Outputs: a private OpenAPI tool server on port `8010`, persistent Qdrant
collections for platform context and ServerClaw memory, a mirrored repo corpus,
a generated local keyword index for memory objects, and a controller-local
bearer token for governed query access.
