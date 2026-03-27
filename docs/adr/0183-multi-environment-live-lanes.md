# ADR 0183: Multi-Environment Live Lanes

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.9
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

The repository already models `production` and a planned `staging` lane, but the operational contract is still uneven:

- many tools hardcode `production` and `staging` directly instead of reading the environment catalog
- the staging subnet is declared in inventory and OpenTofu, but there is no focused host playbook or operator runbook for bringing `vmbr20` up
- future assistants have no clean extension point for a later development lane without another sweep of hardcoded environment checks

This leaves us with a repo that can describe multiple environments, but cannot activate or extend them cleanly.

## Decision

We will treat environment lanes as a catalog-driven contract and add an explicit activation path for staging.

### Environment model

1. `production` remains the required primary environment.
2. `staging` becomes a first-class live lane with a dedicated private bridge and VM declarations.
3. Additional lanes such as `development` are allowed in the topology contract later, but they are not assumed to exist live until they have their own activation path.

### Activation path

1. The environment topology catalog may carry private-network metadata such as bridge name, gateway, and subnet.
2. The Proxmox network automation must be able to render the staging bridge without requiring ad hoc shell edits.
3. Operator runbooks must distinguish clearly between repo-modeled environments and live-applied environments.

### Tooling rule

Tools that accept an environment selector should derive valid environment ids from `config/environment-topology.json` instead of hardcoding a fixed pair whenever that is safe to do so.

## Consequences

**Positive**

- staging gets a deliberate, reviewable activation path instead of living only in placeholders
- future lanes can be added as data and narrow implementation deltas rather than another global hardcoded sweep
- operator documentation becomes honest about what is merely modeled versus what is actually live

**Negative / Trade-offs**

- some older tooling remains specifically `staging -> production` by design, especially promotion logic
- environment topology grows into a stronger contract, so bad catalog edits can affect more tooling if validation is weak

## Implementation Notes

This workstream starts by:

- adding catalog-driven environment selection helpers
- extending environment topology validation with private-network metadata
- wiring the Proxmox network role for the optional `vmbr20` staging bridge
- adding a focused runbook and playbook for staging activation

The first live platform activation completed on 2026-03-27 by applying `vmbr20` plus the staged `docker-runtime` and `monitoring` VMs from `main`.

Repository version `0.177.12` also records the follow-up staging VM module change that keeps Proxmox NIC firewall disabled until staged guest-network-policy automation exists, matching the live state that made the staged guests reachable.
