# ADR 0007: Agent-Oriented Access Model

- Status: Accepted
- Implementation Status: Accepted
- Implemented In Repo Version: N/A
- Implemented In Platform Version: 0.11.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

This repository is intended to be operated collaboratively by humans and coding agents. Proxmox supports both shell-level automation on the node and API-driven automation through role-based users and API tokens.

An agent-friendly design needs:

- deterministic access paths
- explicit least-privilege boundaries
- logs and configuration that survive operator handoffs
- minimal dependence on one human's personal workstation identity

## Decision

We will use a layered access model:

1. Bootstrap layer
   - use the dedicated repo-local SSH key only for initial host bootstrap and emergency recovery
   - keep this path documented and auditable
2. Steady-state automation layer
   - create a dedicated automation identity for routine configuration work
   - prefer Proxmox API tokens for Proxmox object management where possible
   - use Ansible as the primary orchestrator for both host and Proxmox configuration
3. Human operator layer
   - use named human accounts, not shared generic accounts, for routine administration
   - reserve `root@pam` as break-glass access

For agentic operation, every meaningful remote change must satisfy at least one of:

- represented in repository code
- represented in a runbook
- represented in an ADR

## Consequences

- The bootstrap SSH key should be treated as temporary privileged access, not the long-term operating identity.
- Follow-up automation must create the durable non-human identity and rotate away from ad hoc direct-root workflows.
- Proxmox API automation should be preferred for guest, storage, backup, and identity management once the platform is up.
- The Proxmox API token secret must be stored outside git and treated as controller-local secret material.

## Sources

- <https://pve.proxmox.com/pve-docs/chapter-pveum.html>
- <https://pve.proxmox.com/mediawiki/index.php?title=Proxmox_VE_API>
- <https://pve.proxmox.com/pve-docs/index.html>
