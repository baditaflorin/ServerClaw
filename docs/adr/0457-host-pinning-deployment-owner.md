# ADR 0457: Host-Pinning via `proxmox_guests[*].deployment_owner`

> **Superseded by [ADR 0488](0488-single-deployment-per-repo-checkout.md)** (2026-05-17). The multi-deployment substrate is retired; each repo checkout now configures exactly one deployment via `.local/identity.yml`.


- Status: Superseded by ADR 0488
- Implementation Status: Phase 1 (data model + audit script) + Phase 2 (role-side guard `lv3.platform.host_pinning_guard`, wired into `playbooks/public-edge.yml`) implemented. Wiring into other playbooks is per-playbook owner work.
- Date: 2026-04-28
- Concern: multi-deployment-correctness, port-collision, role-side-effects
- Tags: multi-deployment, host-pinning, topology, oauth2-proxy, port-collision
- Implements: follow-up Slice D from [ws-0448 postmortem](../postmortems/2026-04-28-ws-0448-deployment-connection-registry.md)
- Depends on:
  - ADR 0440 (Per-Deployment Identity & Artifact Isolation)
  - ADR 0445 (Phase 1 Multi-Deployment Hardening)
  - ADR 0456 (Deployment-Aware Certificate Validation)

---

## Context

The 2026-04-28 ops.example.org recovery exposed a class of bug the IaC has
no model for. Both `lv3-ops-portal-oauth2-proxy.service` and
`0fork-ops-portal-oauth2-proxy.service` were installed on the same nginx
edge VM, both bound to `127.0.0.1:4180`, and the systemd unit that
started first won the port. The other crashlooped silently. The
operator's only recourse was a manual `systemctl disable` against one
unit — not codified anywhere.

The platform has a per-deployment data layout (ADR 0440), a
per-deployment identity overlay (ADR 0445), per-deployment SSH/connection
metadata (ADR 0448), and now per-deployment cert scoping (ADR 0456).
What it does not have is a record of "this physical VM is exclusively
owned by deployment X". Two deployments declaring the same VM in their
topology is not flagged, and the convergence path has no signal to
refuse to install on a host owned by another deployment.

This ADR adds the data model + the audit primitive. It deliberately
does not modify any role tasks — Phase 2 (role-side enforcement) is a
larger follow-up that should land per-role with role-author review,
because role behavior changes have wider blast radius than data
additions.

## Decision

### 1. Schema: `deployment_owner` on each `proxmox_guests[*]`

The deployment-v1 topology schema gains an optional field on each
guest entry:

```yaml
# .local/deployments/0fork/topology.yml
proxmox_guests:
  - name: nginx
    vmid: 110
    ipv4: 10.10.10.10
    deployment_owner: 0fork    # NEW — pins this VM to the 0fork deployment
```

Slug pattern: `^[a-z0-9][a-z0-9_-]*$` (matches the directory name under
`.local/deployments/`). Optional — omitting it preserves the legacy
shared-VM behavior. Validated by jsonschema in `scripts/deployment.py`.

### 2. Standalone audit primitive: `scripts/host_pinning_check.py`

A read-only script that walks the active (or `--all`) deployment
topologies and reports drift:

- **Error**: a guest's `deployment_owner` value disagrees with the
  deployment whose `topology.yml` declared it. Either move the
  stanza to the correct deployment's topology, or correct the field.
- **Info** (with `--cross`): cross-deployment confirmation that a
  guest is pinned to a particular slug from a sibling deployment's
  topology. Not a drift signal — just a multi-deployment-awareness
  surface.

```bash
# Audit the active deployment
python3 scripts/host_pinning_check.py

# Audit every deployment under .local/deployments/
python3 scripts/host_pinning_check.py --all

# JSON output for downstream tooling
python3 scripts/host_pinning_check.py --all --json
```

Exit codes: `0` clean, `1` drift, `2` usage/data error.

### 3. Phase 2 — role-side enforcement (ws-0459, IMPLEMENTED)

Implemented as a new role `lv3.platform.host_pinning_guard` that:

- Resolves the active deployment slug from
  `active_deployment_slug` extra-var → `$DEPLOYMENT` env → `.local/active-deployment`.
- Looks up the host's `deployment_owner` from `proxmox_guests`.
- Fails the play with a remediation message when slugs mismatch,
  OR when `deployment_owner` is set but no active slug is resolvable
  (strict mode default).
- Skips silently when neither side is set (legacy single-deployment
  behavior preserved).

Wired into `playbooks/public-edge.yml` as the first role so it runs
before `linux_guest_firewall`, `public_edge_oidc_auth`, and
`nginx_edge_publication`. Other playbooks (`ops-portal.yml`,
`keycloak.yml`, etc.) can opt in by adding the same role at the top of
their `roles:` list. Wiring beyond public-edge is deliberately
deferred — each playbook's author should review the change.

## Consequences

- Topologies that adopt `deployment_owner` opt into a new audit
  signal. Topologies that don't use it are unchanged.
- The `host_pinning_check.py` script becomes a candidate for the
  pre-push gate's advisory lane (similar to `validate_catalogue_freshness`
  shipped in ADR 0449). Wiring it in is a one-line follow-up — not
  required by this ADR.
- The `oauth2-proxy@4180` collision class of bug is **not yet**
  prevented at converge time. Phase 2 closes that. ADR 0457 makes the
  data model and audit primitive available so that work can start.

## Operational Notes

```bash
# Add a deployment_owner field to the 0fork topology:
$EDITOR .local/deployments/0fork/topology.yml
# Set proxmox_guests[*].deployment_owner: 0fork on every guest you
# want pinned. Leaving it absent on a guest preserves the legacy
# shared-VM behavior.

# Validate:
python3 scripts/host_pinning_check.py --deployment 0fork

# Cross-deployment audit:
python3 scripts/host_pinning_check.py --all
```

## References

- [ADR 0440 — Per-Deployment Identity & Artifact Isolation](0440-per-deployment-identity-and-artifact-isolation.md)
- [ADR 0445 — Phase 1 Multi-Deployment Hardening](0445-phase1-multi-deployment-hardening.md)
- [ADR 0448 — Per-Deployment Connection Registry](0448-deployment-connection-registry-and-wrapper.md)
- [ADR 0456 — Deployment-Aware Certificate Validation](0456-deployment-aware-certificate-validation.md)
- [2026-04-28 ws-0448 postmortem](../postmortems/2026-04-28-ws-0448-deployment-connection-registry.md) — Slice D in the open follow-ups list.
