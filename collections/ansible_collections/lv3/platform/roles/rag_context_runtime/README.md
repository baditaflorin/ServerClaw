# rag_context_runtime

Deploys the private platform context API and its Qdrant-backed retrieval index on `docker-runtime-lv3`.

Inputs: Docker compose paths, Qdrant image, local embedding backend settings, controller-local API token path, and repo corpus source paths.
Outputs: a private OpenAPI tool server on port `8010`, a persistent Qdrant collection, a mirrored repo corpus, and a controller-local bearer token for governed query access.
