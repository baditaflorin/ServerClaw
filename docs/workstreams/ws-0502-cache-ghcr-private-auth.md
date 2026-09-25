# WS-0502: Cache-only private GHCR upstream authentication

## Decision

Private GitHub Container Registry reads, when required, terminate at a
dedicated loopback-only artifact-cache GHCR adapter. The shared public GHCR
adapter remains anonymous on `10.10.10.80:5002`. The artifact-cache role can
opt into one root-rendered Docker Distribution configuration only for the
separate `127.0.0.1:5005` adapter. It does not render, inspect, copy, or log
any credential material.

## Boundary

The approved cache-only vault renderer must install a regular `root:root`
`0400` file at `/etc/artifact-cache/ghcr-proxy/config.yml` before convergence.
Its two parent directories are fixed `root:root` non-symlink `0700`
directories. That full registry configuration supplies the narrowly scoped
GHCR package-reader credential and is mounted read-only only into the private
GHCR registry's standard configuration path. The broker, builders, public
GHCR adapter, and remaining cache adapters never receive the file or its
contents.

The renderer receives a short-lived `artifact-cache-ghcr-renderer` key only
for the cache-owned `artifact_cache_ghcr_proxy_config` vault record,
atomically writes the file, and revokes that key within the same operation. It
does not leave an API key on VM180. The artifact-cache role remains a
validator/mount consumer and has no secret-fetch logic.

The role refuses private-GHCR mode when the file is missing, not regular, a
symlink, not root-owned, or not mode `0400`; it also rejects a changed path,
parent directory, listener, or storage location. It does not create a
placeholder: an absent file leaves the private adapter absent and private
package pulls fail at the upstream boundary. Private cached layers remain in a
separate `root:root` `0700` directory.

## Apply gate

No secret, deployment, restart, or cache apply belongs to this workstream. A
later controlled apply must prove that the cache-only renderer receipt exists,
the immutable broker digest succeeds only through `127.0.0.1:5005`, a LAN
request to VM180 port `5005` fails, public `:5002` remains anonymous, direct
broker and builder package access remains unavailable, and credential rotation
recreates only the private GHCR adapter.
