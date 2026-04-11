# api_gateway_runtime

Deploys the LV3 unified platform API gateway on `docker-runtime`.

The role builds the FastAPI gateway image from repo-managed sources, copies the canonical gateway and service catalogs into the runtime bundle, and exposes the service on the configured internal port for publication through the NGINX edge.
