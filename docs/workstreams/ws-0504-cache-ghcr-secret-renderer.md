# WS-0504: Cache-only GHCR configuration renderer

## Decision

The private GHCR cache adapter obtains its complete Docker Distribution
configuration through a one-shot read path. Dockerhost keeps the API-key
administration credential local and issues a five-minute, one-use reader only
after an SSH forced-command connection from the artifact-cache VM proves the
dedicated transport key and source address. The reader is not stored on either
host: it is streamed only within the live SSH session, used for the one fixed
vault read, acknowledged, and revoked before the session ends.

The VM renderer accepts no endpoint, record name, output path, or arbitrary
configuration shape. It writes only the fixed private-adapter configuration
file after validating the full Docker Distribution object. Public GHCR cache
traffic remains unauthenticated and no builder can reach the private loopback
adapter.

## Scope

- Dockerhost-only forced-command reader bridge and its root-owned local
  configuration.
- Root-only artifact-cache renderer, atomic file replacement, and non-secret
  receipt.
- A separate, explicit delivery playbook and static security tests.

## Explicitly out of scope

- Creating a GitHub package credential or inserting the vault record.
- Installing a transport private key, public key, or host-key pin; these are
  deployment-local prerequisites.
- Enabling the private cache adapter, changing builder registry routing, or
  exposing a new firewall or gateway port.
- Any broker credential, broker renderer, public catalog, or general vault
  reader functionality.
