# artifact_cache_runtime

Deploys internal pull-through registry mirrors for the container registries the
platform reuses most often, seeds a repo-derived warm set, and can also shut
down the old cache stack when a previous host is being retired during
consumer migration.

## Private GHCR packages

Private package pulls are disabled by default. When explicitly enabled, this
role accepts exactly one pre-rendered Docker Distribution configuration at the
fixed `/etc/artifact-cache/ghcr-proxy/config.yml`. It must be a regular
`root:root` file with mode `0400`, beneath two fixed `root:root` non-symlink
`0700` directories, produced by the approved cache-only vault renderer before
this role runs. That renderer uses a short-lived
`artifact-cache-ghcr-renderer` key for one atomic render from the
`artifact_cache_ghcr_proxy_config` cache-only vault record and revokes the key
in the same operation; no API key is persisted on the cache VM. The role never
fetches, creates, copies, parses, or logs that file.

The configuration is mounted read-only at `/etc/docker/registry/config.yml`
only in the separate bridge-networked `ghcr-private` container, published only
as `127.0.0.1:5005:5000`. The public `ghcr` cache stays anonymous on `:5002`;
the Docker Hub, Plane-artifacts, and n8n mirrors neither receive the mount nor
any upstream package credential. Private cached content lives in a separate
`root:root` `0700` directory. Missing, symlinked, incorrectly owned, or
incorrectly permissioned files make the private-GHCR converge fail before
Compose can change the cache runtime.
