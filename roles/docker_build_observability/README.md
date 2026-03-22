# docker_build_observability

Installs the managed Docker wrapper and Telegraf path that records build events from `docker-build-lv3`.

Inputs: Docker wrapper paths, Telegraf output settings, monitoring token paths.
Outputs: `/usr/local/bin/docker`, a Telegraf config fragment, and `docker_builds` events in InfluxDB.
