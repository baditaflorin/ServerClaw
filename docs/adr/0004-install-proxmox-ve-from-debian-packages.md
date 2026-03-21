# ADR 0004: Install Proxmox VE From Debian Packages

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.2.0
- Implemented In Platform Version: 0.2.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

The host is already running a clean Debian 13 base installation with working SSH access. Proxmox VE 9 can be installed on top of Debian, but Proxmox documents that the ISO installer remains the recommended path for most users and that installing on top of Debian is for advanced users who know their storage and networking choices.

For this repository, the main benefit of the Debian-first path is control:

- the base system is already reachable and inspectable
- package repository state can be codified
- storage and networking can be modeled explicitly in automation
- the installation can remain reproducible from a shell-first workflow

## Decision

We will install Proxmox VE 9 on top of the existing Debian 13 system using official Proxmox package repositories and Ansible-managed configuration.

Initial repository posture:

- use the official Proxmox archive key
- use Debian 13 (`trixie`) package sources
- use the `pve-no-subscription` repository for initial bootstrap unless a paid subscription is added
- do not use `pvetest`
- explicitly disable the `pve-enterprise` repository file unless a valid subscription is present

## Consequences

- We accept the extra responsibility of explicitly managing host networking, storage, and package sources.
- The installation workflow must codify repository setup, package installation, and post-install cleanup.
- If a subscription is later purchased, automation should switch from `pve-no-subscription` to `enterprise`.

## Sources

- <https://pve.proxmox.com/pve-docs-9-beta/chapter-pve-installation.html>
- <https://pve.proxmox.com/pve-docs/pve-package-repos-plain.html>
