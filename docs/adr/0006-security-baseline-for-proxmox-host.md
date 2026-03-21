# ADR 0006: Security Baseline For Proxmox Host

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.13.0
- Implemented In Platform Version: 0.10.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

The Proxmox host will expose SSH and the Proxmox API/UI on a public IP. Proxmox provides built-in firewalling, role-based user management, multiple authentication realms, API tokens, notifications, and certificate management.

Because this node is intended for ongoing human and agent operations, the baseline must reduce accidental exposure without making the system unmanageable.

## Decision

We will apply the following baseline before declaring the node ready for workloads:

1. SSH
   - disable password authentication after bootstrap validation
   - keep key-based SSH only
   - keep an out-of-band provider console path for break-glass recovery
2. Proxmox authentication
   - keep `root@pam` for break-glass administration only
   - create named non-root identities for routine human administration
   - require TFA for human GUI-capable accounts
3. Proxmox API/UI exposure
   - enable and manage Proxmox firewall rules deliberately
   - restrict inbound management access to known management source ranges where practical
   - use trusted TLS certificates, ideally via ACME, before routine browser access
4. Visibility
   - configure notifications early for host and platform events
   - treat backup failures, certificate issues, and storage faults as alerting events

## Consequences

- Bootstrap may temporarily use permissive access while the node is being built, but the steady state must remove password SSH.
- Human operators will have slightly more setup friction because of TFA and separate named accounts.
- Firewall rollout must be tested carefully with an existing SSH session, as Proxmox explicitly warns to open SSH before enabling firewall policy changes.

## Sources

- <https://pve.proxmox.com/pve-docs/chapter-pveum.html>
- <https://pve.proxmox.com/pve-docs/pve-firewall.8.html>
- <https://pve.proxmox.com/wiki/Certificate_Management>
- <https://pve.proxmox.com/wiki/Notifications>
