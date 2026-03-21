# ADR 0003: Prefer Hetzner Rescue Plus Installimage For Bootstrap

- Status: Accepted
- Date: 2026-03-21

## Context

The automatic Robot install and the VNC install path have both been unreliable for this server:

- The wrong operating system installer appeared in VNC.
- SSH key injection has not been trustworthy.
- The VNC path is harder to observe, verify, and automate cleanly.

For this project, the first bootstrap step needs to support inspection, repair, and repeatable installation choices.

## Decision

We will prefer Hetzner Rescue System plus `installimage` for first bootstrap instead of relying on the automatic installer or the VNC installer.

Operationally this means:

1. Boot the server into Hetzner Rescue System.
2. Log in to the rescue environment as `root`.
3. Inspect disks, NIC naming, RAID, and current state from a shell.
4. Run `installimage` and explicitly select Debian 13.
5. If practical, keep the install configuration in a reusable form for future rebuilds.
6. Reboot into the installed system and continue bootstrap via version-controlled automation.

## Consequences

- We get an interactive shell before touching the target disks.
- We can verify the intended OS selection instead of trusting the VNC path.
- We can recover by manually fixing `/root/.ssh/authorized_keys` if needed.
- The first stage is still provider-assisted, but it is more observable and more reproducible than the current VNC flow.
