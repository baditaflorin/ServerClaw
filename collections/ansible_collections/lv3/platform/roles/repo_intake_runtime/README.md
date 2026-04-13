# repo_intake_runtime

Deploy the self-service repository intake application (ADR 0224) on `docker-runtime`.

Conventional paths, the container name, and the local listener port are derived
from `platform_service_registry` (ADR 0373). Inputs here cover the repo-synced
build context, controller-local runtime secrets, and the app-specific session
and gateway settings.
