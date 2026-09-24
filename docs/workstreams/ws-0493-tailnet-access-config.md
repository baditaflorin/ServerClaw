# Provider-neutral tailnet service access

## Scope

Make the network boundary for services such as Gitea explicit, while keeping it
separate from public exposure and service runtime. Keep the mesh client as the
Tailscale client and make its control plane selectable between hosted Tailscale
and self-hosted Headscale.

## Safety

- Default to the repository's currently declared Headscale control plane.
- Do not enroll or migrate live nodes, change ACLs, or publish a tailnet-only
  service publicly in this workstream.
- Require an explicit provider and matching login-server configuration before
  the Tailscale role can run its state-refresh command.
- Refuse to change an enrolled node's active control plane unless a separate
  explicit migration flag is enabled.
- Keep deployment-specific values in host-vars overlays; committed defaults
  remain generic.

## Verification

1. A catalog entry marked `mesh_access: tailnet` is private-only and has a
   repo-managed Tailscale TCP proxy path.
2. Hosted Tailscale is selected with an empty custom login-server URL; Headscale
   requires an HTTPS login-server URL.
3. Invalid provider/URL combinations fail before the role can call `tailscale
   up`; an active control-plane mismatch also fails unless explicitly approved.
4. Service definition generation, catalog validation, focused tests, Ansible
   syntax checks, and the repository standards gate pass.

## Validation record — 2026-09-24

Passed:

- Focused tests: 21 passed across service catalog validation, provider/migration
  guards, and service-definition generation.
- Service catalog schema/topology validation and generated service-definition
  consistency check.
- Repository-wide Ansible syntax matrix and service-definition gate.
- Agent standards, ADR index, workstream registry, generated inventory, topology
  snapshot, and `git diff --check` checks.

Repository-wide `make validate` was also run. It stops at the existing data-model
freshness check because `inventory/group_vars/platform.yml` does not match
`scripts/generate_platform_vars.py` output. This workstream does not change that
generated file or its topology selectors; the mismatch remains recorded for
follow-up instead of regenerating deployment values into the public reference
branch. The public snapshot does not include `config/publication-sanitization.yaml`,
so its private-repository sanitization audit is not available here.

## Deferred live work

This establishes the reusable declaration only. Tailscale ACL changes, split
DNS records, and any Tailscale-to-Headscale cutover remain separate governed
operations with their own backup, access-path, and operator-confirmation gates.

## Coordination

The governed Plane sync rejected the saved local API credential. Git remains
the authoritative workstream record; no alternate credential or manual Plane
write was attempted.
