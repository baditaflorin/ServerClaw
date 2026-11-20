# WS-20261119: NGINX2Root remediation

## Goal

Remove the exposed NGINX remote-code-execution versions from every reachable
server and container, and temporarily block the SCTP kernel module on affected
hosts while the separate kernel issue remains unpatched.

## Status

Inventory found vulnerable NGINX instances in the managed edge, application
containers, Harbor, Coolify, and separately managed Docker deployments. The
official NGINX fixed releases are stable 1.30.7 and mainline 1.31.9. Live
remediation is complete for all 15 NGINX instances in the active inventory
across eight NGINX-bearing hosts. Every runtime reports a fixed version and
passed `nginx -t`; system services are active and the configured container
health checks are green. Per-runtime evidence and the Dify exception are in the
apply receipt.

## Decisions

- Use NGINX's signed official package repository on Debian edge hosts because
  Debian's available packages remain affected.
- Pin container images to vendor digests after confirming NGINX 1.31.9 or later.
- Disable SCTP module autoload only on hosts where the module has no active
  sockets or listeners. Keep this temporary control until a fixed kernel is
  deployed and verified.
- Preserve service data and existing compose configuration while replacing
  vulnerable NGINX runtime layers.
- Use a verified Debian Bookworm NGINX.org binary overlay for Harbor's proxy
  and portal containers, since the packaged Harbor release still ships a
  vulnerable NGINX and a full Harbor upgrade requires its supported migration
  procedure.

## Scope

- Managed NGINX edge package and kernel-module configuration.
- Docker-host kernel-module mitigation on NGINX-bearing hosts.
- NGINX-bearing service image references and their runtime compose deployments.
- External NGINX hosts and image owners discovered in the active fleet.
- A generic remediation runbook, ADR, and live-apply receipt.

## Handoff

The implementation records each host role, container image before and after,
live `nginx -v` result, service health after recreation, SCTP module state, and
the separate Dify zlib exception. A stale builder inventory record was
cross-checked against the live Docker catalog; it has no remaining NGINX
containers. The source change was merged to `main` in PR #707 on 2026-11-19.
Repository version 0.179.66 records the merge; release publication remains
pending. The Woodpecker endpoint was unreachable from Builder CT108 when PR
#707 merged, so that PR has no recorded Woodpecker status. Its remote pre-push
gate reported that all 26 blocking checks passed. PR #710 later fixed the
missing managed-site include on the edge; PR #711 recorded the fresh mainline
reapply, and both push and PR Woodpecker contexts passed. Those later checks
prove the CI route is restored; they do not retroactively validate PR #707.
GitHub's branch-protection API returned HTTP 403 because this private
repository's current plan does not support required status checks.

## Postmortem draft

The standalone response timeline, cost, validation limits, and remaining risks
are recorded in
[`docs/postmortems/2026-11-19-nginx2root-response.md`](../postmortems/2026-11-19-nginx2root-response.md).
