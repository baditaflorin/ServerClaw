# docker_build_observability

Installs the managed Docker wrapper and Telegraf path that records build events from `docker-build`.

Inputs: Docker wrapper paths, socket listener settings, Telegraf config path, service identity, and the shared `guest_observability` framework inputs.
Outputs: `/usr/local/bin/docker`, a framework-managed Telegraf path, and `docker_builds` events in InfluxDB.
