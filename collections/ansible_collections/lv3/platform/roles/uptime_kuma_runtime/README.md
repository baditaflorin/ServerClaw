# uptime_kuma_runtime

Runs Uptime Kuma on the Docker runtime VM through a managed Compose file.

Inputs: site/data paths, compose file path, image, container name, published port, and Docker Compose plugin availability.
Outputs: a pulled image, running container, and verified local listener on the runtime VM.
