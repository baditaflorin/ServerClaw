# ADR 0042: step-ca For SSH And Internal TLS

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The platform already has:

- Tailscale-backed private operator access under ADR 0014
- named non-root host and guest administration under ADR 0018
- durable API automation for Proxmox object management

It does not yet have a first-class internal certificate authority for:

- short-lived SSH user certificates for humans and agents
- SSH host certificates for the Proxmox host and guests
- internal X.509 certificates for private APIs and service-to-service mTLS

That gap keeps routine access tied too closely to long-lived SSH keys and ad hoc certificate handling.

## Decision

We will standardize on `step-ca` as the internal certificate authority for LV3.

Initial scope:

1. issue SSH user certificates for named operators and approved automation identities
2. issue SSH host certificates for the Proxmox host and managed guests
3. issue private X.509 certificates for internal HTTPS and mTLS endpoints
4. expose a private CA API reachable only from trusted LV3 networks

Initial placement:

- host: `docker-runtime-lv3`
- exposure: private-only, not published on the public edge
- trust bootstrap: repo-documented CA URL and fingerprint, with secrets kept outside git

Provisioners must be separated by identity class:

- humans
- agents
- services
- hosts

## Consequences

- Routine SSH access can move from long-lived keys toward short-lived certificates.
- Internal API publication can reuse one certificate authority instead of per-service self-signed material.
- `sshd` trust on the Proxmox host and guests becomes CA-based rather than key-copy based.
- CA backup, recovery, and root or intermediate key handling become critical control-plane responsibilities.

## Boundaries

- `step-ca` is the default issuer for SSH and internal X.509 certificates.
- It is not the source of truth for arbitrary application secrets or API passwords.
- Public HTTPS certificates for internet-facing services still follow the existing Let's Encrypt edge model unless a future ADR replaces it.

## Sources

- [step-ca Certificate Authority Overview](https://smallstep.com/docs/step-ca)
- [Getting Started with step-ca](https://smallstep.com/docs/step-ca/getting-started/)
- [Basic Certificate Authority Operations](https://smallstep.com/docs/step-ca/basic-certificate-authority-operations)

