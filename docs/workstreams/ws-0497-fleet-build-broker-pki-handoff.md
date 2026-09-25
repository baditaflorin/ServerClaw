# WS-0497: Fleet build broker root-only PKI handoff

## Goal

Provide the executable, testable control-plane handoff that issues and renews
the private fleet-build-broker's 24-hour mTLS leaves without placing a CA
provisioner, dedicated client-CA key, or vault write credential in the broker
workload.

## Boundaries

- No certificate, API key, provisioner secret, or deployment-specific network
  value is committed.
- No certificate issuance, vault write, Ansible apply, or deployment occurs in
  this workstream.
- The broker runtime role remains separately owned. This workstream defines
  only its PKI and secret-delivery contract.

## Result

The new root-only handoff validates the exact DNS/IP server SAN contract, the
two builder and one monitor SPIFFE identities, and the renderer-consumer
boundaries before it can invoke Step-CA. It validates all replacement leaves
in a private temporary directory, then submits the complete delivery batch on
standard input to the canonical short-lived `infra-privileged` writer bridge.
The bridge is required to issue and revoke its five-minute key transactionally.

The handoff records only safe lifecycle timestamps. At 80% of the 24-hour
lifetime it renews; failures are non-zero and the health mode fails closed,
which exposes the renewal deadline to the normal systemd/monitoring alert
path before any leaf can expire.

## Integration prerequisite

The deployment/control-plane integration must install the canonical writer
bridge. The role bootstraps and then verifies its own root-only,
broker-exclusive self-signed client trust anchor; it does not accept the
platform root, platform client issuers, or a cross-signed fallback as broker
client trust. The normal renewal path never rotates that anchor automatically:
it fails seven days before the 90-day trust-anchor expiry so a reviewed,
coordinated client/broker rotation can be scheduled. The role intentionally
has no OpenBao, default-token, bearer-token, workload-credential, or global
client-trust fallback.

The executable is a rendered role template, not a `files/` asset. The
installation task must therefore use Ansible's `template` module so a fresh
control-plane convergence can install it before any client-CA bootstrap,
timer enablement, certificate issuance, or vault transaction.
