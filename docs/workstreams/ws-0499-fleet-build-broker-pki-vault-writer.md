# WS-0499: Dockerhost broker PKI vault writer

## Decision

The broker PKI control host never receives a persistent vault credential or
the Dockerhost API-key administration credential. Instead it can reach a
single Dockerhost account through a source-pinned SSH key. OpenSSH discards the
requested command and invokes one exact sudo-approved transaction, which is
also independently validated by the root-only executable.

The transaction accepts exactly the ordered ten-record broker PKI batch. It
issues one 300-second, one-use writer with the fixed broker renewer identity
and authority, sends exactly one HTTPS batch request, then attempts revocation
in all outcomes. It has no general issue, revoke, list, read, render, retry, or
interactive mode. Certificate and credential values remain in process memory.

## Scope

- Dockerhost-only Ansible role and collection/root playbooks.
- Root-only Python transaction executable and non-secret configuration.
- Forced SSH command, restricted system account, exact sudo rule, and focused
static tests.
- Operating runbook for non-retry handling of ambiguous issuance.
- Privilege-safe `AuthorizedKeysFile` traversal for the restricted account;
  the public key remains immutable and the transaction configuration remains
  root-only.
- A runtime validation invariant that permits only the fixed config directory's
  exact `root:writer-group 0710` traversal boundary; all other protected
  parents remain `root:root` and non-writable.

## Explicitly out of scope

- Creating the dedicated transport private key or any local credential.
- Deploying `go-apikey-service` or `go-fleet-secrets` releases.
- Issuing certificates, writing a vault record, applying the playbook, or
  starting the broker.
- Public routing, catalog registration, cache configuration, and image release.
