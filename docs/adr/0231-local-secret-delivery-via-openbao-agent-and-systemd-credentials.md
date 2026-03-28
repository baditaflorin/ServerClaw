# ADR 0231: Local Secret Delivery Via OpenBao Agent And Systemd Credentials

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.39
- Implemented In Platform Version: 0.130.38
- Implemented On: 2026-03-28
- Date: 2026-03-28

## Context

ADR 0077 already covers Compose-side secret injection, but server-resident
operations will also introduce host-local control loops such as:

- `ansible-pull` timers
- `systemd-run` wrappers
- local policy bundles
- release-bundle verifiers
- recovery agents

Those components need a host-native secret contract that does not push
credentials back into repo workspaces or long-lived shell environments.

## Decision

We will standardize host-local secret delivery on **OpenBao Agent plus systemd
credentials**.

### Delivery model

- OpenBao Agent authenticates with the appropriate host or service identity
- secrets are rendered into memory-backed runtime locations under `/run` or the
  systemd credentials path
- systemd-managed services consume them through `LoadCredential=` or equivalent
  file-backed credential mounts
- rotated credentials are refreshed through the same agent path rather than by
  rewriting repo-managed files

### Security rule

- server-resident automation must not depend on secrets stored in the Codex
  session, local workstation shell history, or long-lived plaintext files in
  the repo checkout
- any host-local bootstrap material that remains on disk must be narrow,
  low-privilege, and explicitly documented

## Consequences

**Positive**

- Server-side loops can authenticate and operate without leaking secrets into
  the authoring environment.
- Host-native services gain a first-class secret delivery path.
- Secret rotation becomes less coupled to human re-runs.

**Negative / Trade-offs**

- Host-local agent supervision and template governance become more important.
- Operators need to debug both systemd credentials and OpenBao Agent state.

## Boundaries

- `step-ca` remains the preferred certificate issuer; this ADR governs secret
  and token delivery, not certificate authority ownership.
- This ADR extends the runtime secret model to host-native services; it does not
  replace the existing Compose-side contract overnight.

## Related ADRs

- ADR 0043: OpenBao for secrets, transit, and dynamic credentials
- ADR 0047: Short-lived credentials and internal mTLS
- ADR 0077: Compose runtime secrets injection via OpenBao Agent
- ADR 0170: Platform-wide timeout hierarchy
- ADR 0224: Server-resident operations as the default control model
