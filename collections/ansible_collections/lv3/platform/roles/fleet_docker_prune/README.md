# fleet_docker_prune

Keeps the Docker storage of a fleet build host from filling `/`. It installs one systemd timer that removes only what
nothing is using:

- images that no container (running or stopped) references and that are older than `fleet_docker_prune_image_max_age`
  (default 7 days), via `docker image prune -af --filter until=...`;
- BuildKit build cache older than `fleet_docker_prune_builder_cache_max_age` (default 7 days), via
  `docker builder prune -af --filter until=...`.

It never touches containers, volumes or networks, so a running Woodpecker step is not affected; a pruned image is simply
pulled again by the next pipeline that needs it.

Why it exists: a Woodpecker step on the 0mcp `docker-build` guest died with `no space left on device` while compiling
(`/tmp/go-build...` lives in the container's writable layer on `/`). Nothing pruned that host, and `/` sat at 83%.

After each run the script writes two node_exporter textfile metrics (when `fleet_docker_prune_textfile_dir` is set):
`fleet_docker_prune_last_success_timestamp_seconds` and `fleet_docker_prune_reclaimed_bytes`. The alert
`FleetDockerPruneStale` in `config/prometheus/rules/fleet-disk.yml` fires when a managed host has not pruned for 3 days.

Run it like the other fleet roles: `playbooks/fleet-observability.yml --limit <one host> --check --diff` first.
