# fleet_build_broker_pki_handoff

Installs the root-only certificate lifecycle handoff for the private
`fleet-build-broker` mTLS endpoint. It is deliberately separate from the
broker runtime role: the workload receives rendered leaf material only and
never receives the Step-CA services provisioner, the dedicated client-CA key,
or vault write authority.

## Contract

- Every broker server/client leaf has a 24-hour lifetime.
- Renewal begins at 80% elapsed lifetime (19h 12m) and a failed renewal exits
  non-zero. The health mode also fails once that deadline passes, making the
  alert/fail-closed condition observable before expiry.
- The server leaf contains exactly `fleet-build-broker.internal` and the
  deployment-provided private IP as SANs, with `serverAuth`.
- The only client leaves are the two builder SPIFFE identities and the broker
  monitor SPIFFE identity. Each is `clientAuth` only.
- The broker trusts exactly one broker-exclusive, self-signed client CA. It is
  not chained to the platform root, so a certificate from another platform
  client issuer cannot authenticate to the broker. Its public certificate is
  delivered only to `fleet-build-broker-runtime-renderer`; its private key is
  root-only local issuer state and never enters `go-fleet-secrets`.
- The platform Step-CA root is used only to validate and distribute the
  broker's server certificate to its callers. It is never accepted as broker
  client trust and is never provided to the broker workload for that purpose.
- The rendered broker and monitor secret consumers are exactly
  `fleet-build-broker-runtime-renderer` and
  `fleet-build-broker-monitor-renderer`; each builder receives only its own
  leaf pair plus the server trust bundle.

## Vault writer boundary

`fleet_build_broker_pki_vault_writer_command` is a mandatory, root-only
deployment integration. Its `transaction` subcommand receives the complete
secret batch on standard input and must:

1. issue one five-minute `infra-privileged` API key for
   `fleet-build-broker-pki-renewer` through the canonical API-key admin path;
2. use that key to write the complete batch to `go-fleet-secrets`;
3. revoke the key in a `finally` path, including when the write fails; and
4. emit no material values, API keys, or provisioner values.

The handoff will refuse to issue or publish if this command is absent or the
configuration diverges from the fixed identity/consumer contract. The command
must provide an atomic batch guarantee (or leave the prior batch active), so a
renderer can never observe a newly published certificate with an old private
key.

## Dedicated client trust-anchor lifecycle

During a root-owned convergence, the handoff's `--bootstrap-client-ca` mode
either validates the existing anchor or creates the anchor once. It is a
P-256, self-signed CA named `fleet-build-broker-client-ca`, stored below the
handoff state directory in a root-owned `0700` directory. The private key is
`0400`; the public certificate is `0444`; symlinks, partial material, unsafe
permissions, non-root ownership, a non-CA certificate, and a platform-root
chain are rejected.

The anchor is valid for 90 days and the normal renewal timer starts failing
seven days before it expires. The timer never rotates a client CA on its own:
changing a trust anchor requires a deliberate, reviewed client/broker rollout
with overlap and a separately approved root-only replacement procedure. That
avoids silently invalidating live builder or monitor mTLS clients. Regular 24-hour client
leaves are signed directly by this anchor and are verified against only this
public certificate; no global or platform client trust bundle participates.

Use `--check-config` and `--plan` in a non-production harness first. Only the
systemd service's `--renew` mode is capable of leaf issuance or vault delivery.
`--bootstrap-client-ca` is separately root-only and never issues leaves or
writes the vault; `--check-client-ca` validates the existing trust anchor.
