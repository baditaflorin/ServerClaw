# ADR 0001: Bootstrap Dedicated Host With Ansible

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.2.0
- Implemented In Platform Version: 0.1.0
- Implemented On: 2026-03-21
- Date: 2026-03-21

## Context

This repository is intended to manage a dedicated Hetzner server that will become a Proxmox VE host.

Unlike cloud instances, a dedicated server cannot be fully created from zero using only in-band automation when there is no working remote access path yet. There is an unavoidable provider-controlled bootstrap boundary:

- OS activation happens in Hetzner Robot
- The first reboot after activation is provider-triggered or out-of-band
- Recovery may require Rescue System or VNC/console access

## Decision

We will treat the build as two stages:

1. Out-of-band bootstrap
   - Gain initial `root` access
   - Ensure SSH key login works
   - Confirm the host is running the intended base OS
2. In-band infrastructure as code
   - Use Ansible for host bootstrap, package configuration, repository setup, hardening, and Proxmox installation
   - Keep all host changes declarative and committed in this repository

## Consequences

- The very first recovery/login step is documented, but not fully automatable.
- After SSH access exists, all subsequent host configuration must be reproducible from code.
- Manual shell changes on the host should be avoided unless they are immediately codified in the repo.
