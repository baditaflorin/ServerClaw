# artifact_cache_ghcr_secret_renderer

Root-only artifact-cache renderer for the one fixed private GHCR proxy
configuration. It gets a transient reader from the Dockerhost forced-command
bridge over pinned SSH stdio, reads only `artifact_cache_ghcr_proxy_config`,
validates the complete Docker Distribution configuration, and atomically
writes `/etc/artifact-cache/ghcr-proxy/config.yml` with mode `0400`.

It installs no API key. Its only persistent transport material is a
deployment-local root-only SSH key that the Dockerhost bridge restricts to one
command and one source. The receipt records no secret or secret-derived value.
