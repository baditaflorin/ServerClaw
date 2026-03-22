# ADR 0043: OpenBao For Secrets, Transit, And Dynamic Credentials

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-22

## Context

The repository already has controller-local secret handling guidance under ADR 0034, but the platform still lacks an internal secrets authority for:

- API keys used by applications and agents
- service credentials that should not live in repo-managed files
- cryptographic operations such as encrypt, decrypt, sign, and verify
- future dynamic or short-lived credentials issued to workloads

As the system becomes more agentic, the risk from static shared secrets rises quickly.

## Decision

We will use OpenBao as the platform secret authority.

Initial responsibilities:

1. store application and automation secrets outside git
2. expose a private HTTP API for secret retrieval and rotation workflows
3. provide Transit for encryption, signing, and other cryptographic operations
4. provide machine-oriented auth methods for services and agents
5. support dynamic credentials where that meaningfully reduces secret lifetime

Initial placement:

- host: `docker-runtime-lv3`
- exposure: private-only, never published directly on the public edge
- storage: single-node durable storage with backup coverage under the control-plane recovery policy

Authentication and authorization must be structured around narrow roles:

- named humans
- named agents
- named services
- break-glass operators

## Consequences

- Repo-local secret files stop being the long-term operating model for internal services.
- Agents can receive scoped credentials instead of reusing human or global service tokens.
- Cryptographic operations that currently tempt ad hoc shell handling can move behind a controlled API.
- Bootstrap, unseal or recovery handling, and audit review become part of regular platform operations.

## Boundaries

- OpenBao is the default authority for secrets, tokens, and encryption operations.
- `step-ca` remains the default issuer for SSH and internal X.509 certificates.
- OpenBao PKI or SSH engines may be used later only when there is a clear reason not to use the default `step-ca` path.

## Sources

- [What is OpenBao?](https://openbao.org/docs/what-is-openbao/)
- [AppRole auth method](https://openbao.org/docs/auth/approle/)
- [Transit secrets engine](https://openbao.org/docs/secrets/transit/)
- [PKI secrets engine API](https://openbao.org/api-docs/secret/pki/)

