# Artifact-cache private GHCR secret renderer

## Purpose

This runbook governs delivery of the private GHCR adapter's complete Docker
Distribution configuration. It is deliberately separate from both the public
GHCR cache and the fleet build broker. The public adapter remains anonymous;
the private adapter is loopback-only and is not a builder endpoint.

## Preconditions

1. The private-adapter IaC contract from WS-0502 is merged and its adapter is
   still disabled.
2. A dedicated cache-owned package-read credential has been created through
   the approved credential workflow. Do not reuse a builder, broker, GitHub
   App, or emergency fallback credential.
3. The vault contains exactly `artifact_cache_ghcr_proxy_config`, whose sole
   consumer is `artifact-cache-ghcr-config-renderer`. The value is a complete
   JSON-as-YAML Docker Distribution configuration; it is never a raw token or
   Docker client configuration.
4. The root-only artifact-cache SSH transport private key, its exact labelled
   public half, and pinned Dockerhost host-key entries exist in deployment-local
   state. Do not generate them in this playbook or commit them.
5. `go-apikey-service` has the atomic one-use claim release and
   `go-fleet-secrets` has direct trusted-key verification with consumer ACLs.

The value must have this exact structural boundary. `username` and `password`
are the only dynamic fields and must be nonempty single-line credentials.

```json
{
  "version": "0.1",
  "log": {"level": "warn"},
  "storage": {
    "filesystem": {"rootdirectory": "/var/lib/registry"},
    "delete": {"enabled": true}
  },
  "http": {"addr": "0.0.0.0:5000"},
  "proxy": {
    "remoteurl": "https://ghcr.io",
    "username": "<cache-only-package-reader>",
    "password": "<cache-only-package-token>"
  }
}
```

No additional registry middleware, listener, storage, upstream, or credential
field is accepted. JSON is valid YAML for Docker Distribution and permits the
renderer to use a standard-library parser without adding a YAML dependency.

## Delivery contract

Run `playbooks/artifact-cache-ghcr-secret-renderer.yml` only after the
preconditions are verified. It first converges Dockerhost's forced-command
bridge, then the artifact-cache renderer. The renderer sends only a fixed
`REQUEST` frame over pinned SSH stdio. The bridge mints one 300-second,
one-use `infra-privileged` reader for the sole cache renderer identity and
streams it in memory through that same channel. The renderer reads only the
fixed vault record over HTTPS with proxying and redirects disabled.

On a valid read it atomically replaces only:

- `/etc/artifact-cache/ghcr-proxy/config.yml` — `root:root`, regular file,
  mode `0400`; parent directories are non-symlink `root:root` mode `0700`.
- `/var/lib/artifact-cache/ghcr-proxy-renderer/last-render.json` — root-only,
  non-secret receipt with no value, hash, token, response metadata, or secret
  fingerprint.

The renderer then acknowledges `CONSUMED`; the bridge revokes the reader before
returning. If validation, write, acknowledgement, or revocation fails, the
delivery command fails and the bridge attempts revocation. It does not retry.

After a successful receipt and file-mode check, enable the private adapter
through the WS-0502 artifact-cache contract. Verify the container's internal
listener uses `0.0.0.0:5000`, while the host publishes the adapter only on its
private loopback port. Prove that the public GHCR cache remains anonymous and
that no external or builder route reaches the private adapter.

## Failure handling

An ambiguous delivery is not safe to retry blindly: inspect the non-secret
receipt and the vault/API-key audit trail first. A reader is one-use and
short-lived even if revocation reporting fails, but a revocation failure is a
security incident until reconciled. Never bypass a delivery failure with a
direct GHCR pull, an environment variable, a host file copied by hand, or a
broker credential.
