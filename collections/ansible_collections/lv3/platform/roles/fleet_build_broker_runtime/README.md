# fleet_build_broker_runtime

Converges the private `go-fleet-build-broker` stack on VM180 after the
root-only `go-fleet-secrets` renderer has completed.

The role deliberately refuses direct `ghcr.io` images and mutable tags. Its
only accepted image form is an immutable digest served by VM180's loopback-only
private GHCR cache listener (`127.0.0.1:5005`). The public
`<artifact-cache-ip>:5002` adapter remains anonymous for normal builder and
runtime use. Private GHCR cache authentication remains a cache-owned concern:
this role neither creates, reads, nor installs a package token.

The role creates only the empty non-secret directories. Before each Compose
converge it removes any prior renderer container and runs the broker image's
two root-only `render-secrets` commands. Each command receives a different
owner-only deployment API-key file and a committed non-secret, target-specific
allowlisted manifest. The runtime principal can read only server TLS/client CA
and GitHub entries; the monitor principal can read only server CA and monitor
client entries. API keys and all rendered values remain outside this
repository. Each renderer bind-mounts only its own manifest file, never the
shared manifest directory.

- `/var/lib/fleet-build-broker` is owned by UID/GID `10001` with mode `0750`;
- `/run/go-fleet-secrets/fleet-build-broker` is `root:10001` with mode `0750`;
  and
- its seven server/GitHub secret files are `root:10001` with mode `0440`,
  mounted read-only into the UID/GID `10001` broker container.

The monitor certificate, monitor key, and server CA are rendered separately to
`/run/go-fleet-secrets/fleet-build-broker-probe` as `root:root`, mode `0700`
for the directory and `0400` for files. That directory is available only to
the monitor-scoped root renderer and the separately managed host-side mTLS
probe; it is never mounted into the broker or runtime renderer. The Docker health check uses the image's offline
`/fleet-build-broker healthcheck` command. The deployment runner's host-side
mTLS probe is authoritative for network and certificate behavior.

The only network publication is `artifact-cache-ip:18100 -> container:5001`.
Guest policy permits it solely from the two declared builder addresses; there
is no public route, DNS declaration, catalog entry, or OpenBao/AppRole path.
