# Workstream ws-0524: ServerClaw snapshot CI compatibility

## Goal

Keep the generic ServerClaw Proxmox host template compatible with the source repository's validation tests, without copying deployment-specific firewall rules into the public template or weakening the private live-policy assertion.

## Scope

- Mark the Tier A Proxmox host template as a generic publication profile.
- Skip only the deployment-specific Scanopy relay firewall assertion when that exact generic template is under test.
- Preserve the private inventory assertion and the sanitization leak guard.

## Validation

- The original failure was reproduced in both public Woodpecker pipelines for the same `KeyError` on `proxmox_host_additional_tcp_rules`.
- The unchanged private inventory assertion passes.
- The sanitized template fixture skips the deployment-only assertion explicitly.
- The exact public CI test command passes locally; the full repository gate is being completed before publication is refreshed.
- The remote full-source gate also found dangling scan-receipt pointers for Authentik and Typesense. The Authentik digest was rescanned from its tracked SBOM with Grype 0.111.0; its catalog remains blocked at 4 Critical / 96 High. Typesense now points to its tracked same-digest March 30 receipt, without claiming that evidence is fresh.

## Next

Complete. Private PR #349 merged to `main` at `bbc8ab5f3`; the sanitized snapshot passed both Woodpecker checks and public PR #72 merged at `4db0a679`. The patch release bump remains pending the canonical release process, which is blocked by active workstreams elsewhere in the repository.
