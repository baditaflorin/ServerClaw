# ADR 0498: Patch NGINX RCEs and contain the SCTP escalation path

- Status: Accepted
- Implementation Status: Implemented live and merged to main; Woodpecker status unavailable at merge
- Implemented In Repo Version: 0.179.66 (merged by PR #707; release not yet cut)
- Implemented In Platform Version: 0.179.63 (version live during application; no stack version change)
- Implemented On: 2026-11-19
- Date: 2026-11-19
- Concern: security
- Tags: nginx, security, containers, sctp

## Context

The NGINX advisory lists the affected versions and fixed releases for the five
reported issues. The fixed Open Source releases are stable 1.30.7 and mainline
1.31.9. Vulnerable NGINX packages and container images were found on system
edges, application runtimes, Harbor, Coolify, and separately managed Docker
hosts. Several application images bundle NGINX and cannot be safely replaced
without upgrading the whole application.

The demonstrated privilege-escalation chain also depends on SCTP kernel
support. The inspected NGINX hosts had modular SCTP support but no SCTP sockets
or listeners. Blocking the unused module provides temporary containment while
the kernel issue is addressed separately.

## Decision

1. Replace system NGINX with the signed NGINX.org stable package 1.30.7, or
   mainline 1.31.9 when retaining a mainline installation. Back up the existing
   configuration tree, preserve required modules, validate the final config,
   and restart only after validation succeeds.
2. Pin service-owned NGINX images to a verified fixed digest. For application
   images that bundle an older NGINX, first validate a replacement binary
   against the existing configuration, mounted files, and runtime libraries;
   then add a read-only Compose bind mount and keep a pre-change Compose backup.
3. For Harbor, patch only its NGINX proxy and portal binaries. Do not use a
   full Harbor minor-version upgrade as the emergency fix because Harbor
   upgrades can include database and data migrations.
4. Install a persistent SCTP module block only on hosts where the active
   kernel supports SCTP as a module and the host has no SCTP sockets. Keep this
   temporary control until a fixed kernel is installed and verified.
5. Track unrelated image vulnerabilities in their own scan receipt and
   exception. Do not describe the NGINX patch as resolving those findings.

## Implementation and verification

On 2026-11-19, all 15 NGINX runtime instances in the active inventory were
updated across eight NGINX-bearing hosts. System NGINX packages now report
1.30.7. Container NGINX reports 1.30.7 or 1.31.9. `nginx -t` passed in all
15 runtimes; all three system services were active. The eight configured
container health checks were healthy after rollout; the remaining containers
without health checks were running with valid configuration.

Harbor's fixed 1.30.7 executable came from the official Debian Bookworm package
`nginx_1.30.7-1~bookworm_amd64.deb`. Its SHA-256 matched the official package
index, and the extracted executable passed `nginx -t` against both Harbor
configurations in cloned containers sharing the original network. The live
proxy and portal containers both became healthy after recreation.

The SCTP module block was applied to all eight NGINX-bearing hosts after
confirming modular support and no active SCTP sockets. A read-only Scanopy
inventory also showed a stale NGINX-named builder service last seen on
2026-11-07; the current builder Docker inventory had no NGINX containers.

The Dify NGINX image now uses the fixed 1.30.7 Alpine digest. Its image scan
still reports one separate critical zlib finding with no vendor fix, plus
eight high and five medium findings. A one-week exception through 2026-11-26
tracks reassessment of that zlib finding. The Ansible post-deploy health probe
could not resolve the inventory hostname from the controller; direct checks
on the host returned HTTP 200 and the Dify NGINX container was healthy.

See the workstream and live-apply receipt for backup paths, image digests,
runtime results, and the remaining Dify exception. The repo changes were
merged to main by PR #707. The Woodpecker pipeline could not reach
`ci.example.org` from Builder CT108, so no CI status was reported; the remote
pre-push gate reported all 26 blocking checks passed. The repository version
is 0.179.66, while 0.179.63 remains the live platform version because the
merged work has not been applied from main and no platform stack version
change was made.

## Consequences

- The reported NGINX issues are fixed in the identified active runtimes.
- SCTP remains blocked until the separate kernel fix is deployed and verified.
- Bind-mounted NGINX binaries must be reviewed whenever their owning Compose
  project or base image is regenerated or upgraded.
- Harbor reconfiguration may regenerate its Compose file; retain the documented
  bind mounts when running Harbor's `prepare` workflow.
- Dify's zlib exception remains separate and expires on 2026-11-26.
