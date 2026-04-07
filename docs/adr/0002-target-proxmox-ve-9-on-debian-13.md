# ADR 0002: Target Proxmox VE 9 on Debian 13

- Status: Accepted
- Implementation Status: Accepted
- Implemented In Repo Version: N/A
- Implemented In Platform Version: 0.2.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

The target platform is a fresh Debian 13 dedicated server that should become a Proxmox host.

Proxmox Server Solutions announced Proxmox VE 9.0 on 2025-08-05, and that release is based on Debian 13 "Trixie". Proxmox also states that Proxmox VE 9.0 can be installed on top of Debian.

Sources:

- <https://www.proxmox.com/en/about/company-details/press-releases/proxmox-virtual-environment-9-0>
- <https://pve.proxmox.com/pve-docs-8/chapter-sysadmin.html>

## Decision

We will target:

- Debian 13 as the base operating system
- Proxmox VE 9 as the intended major version
- Repository-based installation on top of Debian, not an ad hoc manual conversion

## Consequences

- Automation should assume Debian 13 package names and repository layout.
- The no-subscription repository may be used initially unless an enterprise subscription is provisioned.
- Version pinning and upgrade guidance should be added before production use.
