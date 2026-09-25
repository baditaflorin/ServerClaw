# Fleet-build-broker PKI vault-writer runbook

## Purpose

This runbook governs the one-shot bridge that lets the Step-CA broker PKI
handoff publish its exact certificate batch without granting it a persistent
vault writer or the Dockerhost API-key administration credential.

## Preconditions

1. `go-apikey-service` at or above the release containing atomic single-use
   claims is deployed and healthy.
2. `go-fleet-secrets` at or above the release containing the fixed
   `/broker-pki-batch` endpoint is deployed and healthy.
3. A dedicated Ed25519 key pair exists only for the Step-CA-control-host to
   Dockerhost forced-command transport. Its private half is root-only control
   plane state; the public half is supplied through the deployment-local
   overlay with the exact `fleet-build-broker-pki-runtime-control` label.
4. The Dockerhost local API-key administration file already exists, is owned by
   root, is a regular non-symlink file, and is not readable by group or other.
5. The `fleet-build-broker-pki-vault-writer` playbook has been converged on
   Dockerhost and `sshd -t` was validated by the role.

The SSH authorization file contains only the transport public key and exact
forced-command policy. It is root-owned, group-read-only, and stored in a
root-owned directory that is execute-only for the restricted account; this is
the minimum access OpenSSH needs when it resolves `AuthorizedKeysFile` after
dropping privileges. The transaction executable accepts that directory only as
the fixed transaction-config parent and requires its exact `root:writer-group`
`0710` boundary; all other configuration parents remain root-only and
non-writable. The transaction configuration and all credentials remain
root-only (`0600`), and the restricted account cannot list the directory or
read either file.

## Invocation contract

Only the root-only PKI handoff calls the bridge. Its SSH client must disable a
TTY and use the dedicated key; it sends the transaction JSON on standard input.
The server ignores any requested remote command and permits only this exact
operation:

```
transaction --principal fleet-build-broker-pki-renewer --scope infra-privileged --ttl-seconds 300
```

The bridge independently verifies the ten fixed records and recipients,
creates one five-minute, one-use writer, performs one HTTPS batch request, and
always attempts revocation after issuance. It never persists or emits secret
values. It is not an interactive operator command.

## Failure handling

- If issuance fails, no vault request is made.
- If the batch request fails or is ambiguous, the bridge attempts revocation,
  exits non-zero, and performs no retry.
- If revocation fails, it exits non-zero even if the batch endpoint accepted the
  request. The key is still limited to one use and five minutes, but the
  operational alert must be treated as a security incident.
- Before any new issuance after an ambiguous failure, inspect the fixed batch
  audit trail and certificate state. Do not retry blindly.

No public route, catalog entry, gateway exposure, fallback credential, or
long-lived writer is part of this bridge.
