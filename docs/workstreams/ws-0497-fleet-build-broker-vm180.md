# WS-0497: VM180 fleet-build-broker IaC baseline

## Decision

The broker is deployed as a separately invoked, private-only Compose stack on
the existing `artifact-cache` VM (VM180). It is deliberately not added to the
public service catalog, DNS, NGINX, or OpenBao service registry.

The Compose contract publishes `artifact-cache-ip:18100` to container port
`5001`. The canonical guest firewall permits that port only from the two
approved builder source addresses declared in inventory. The broker still
requires mTLS; the network restriction is a second boundary, not an
authentication substitute.

## Image and secret delivery

The role refuses direct `ghcr.io` image references and mutable tags. It accepts
only an immutable `sha256` image from VM180's existing GHCR cache listener on
port `5002`. This avoids distributing a GitHub package credential to either
builder or the broker runtime.

At this point the cache's GHCR adapter only supports anonymous upstream pulls.
Private package support is therefore a separate cache-owned prerequisite. Its
future credential must be a narrowly scoped package-read identity rendered by
the root-only secret renderer into the cache's own root-managed configuration;
it must not be a broker, builder, OpenBao, or per-VM credential. No such value
is created or stored by this workstream.

`go-fleet-secrets` is the only broker secret authority. The IaC role creates
only empty non-secret directories, verifies two independent root-only renderer
API-key files, then invokes the immutable broker image's `render-secrets`
command twice before the non-root broker starts. The runtime and monitor
principals have separate consumer ACLs and non-secret manifests. Each target
rejects missing, mixed, or cross-target filenames before fetching any value,
and each renderer bind-mounts only its own manifest file.

The broker's server/GitHub render directory and seven runtime files are
`root:10001` with modes `0750` and `0440`, respectively. The monitor
certificate/key and server CA are instead rendered into a separate
`root:root` host-probe directory with modes `0700` and `0400`. The Compose
broker service never mounts that probe directory, and the runtime renderer
never mounts or reads it. Its Docker health check is the image's offline health
command; the deployment runner's separately managed root-only mTLS probe is
authoritative for certificate and network behavior. The role checks all file
shapes and permissions but never writes or logs values. The fallback PAT
remains runtime-only and is still selected only by the broker's
primary-credential failure policy.

## Apply gate

Do not run the new playbook until all of these are true:

1. A signed/verified immutable broker image is available through VM180:5002.
2. The cache-owned private-GHCR authentication path has been exercised for that
   exact digest without exposing a token to the broker or builders.
3. Separate go-fleet-secrets renderer receipts prove the runtime and root-only
   probe directories are current and that each target's API-key principal is
   limited to its approved consumer secrets.
4. The private post-deploy mTLS, deny-path, replay, checksum, and fallback
   tests in the broker operations runbook have been completed.

No live apply, catalog publication, route, or release change is part of this
workstream.
