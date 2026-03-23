# ADR 0065: Secret Rotation Automation With OpenBao

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.62.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-22
- Date: 2026-03-22

## Context

After ADR 0043 (OpenBao) and ADR 0047 (short-lived credentials), the platform has the infrastructure to issue and renew credentials. However:

- no policy enforces when long-lived credentials must be rotated
- service accounts that do not use dynamic credentials still rely on static secrets that were set at initial provisioning
- there is no automated process to detect credentials approaching expiry and initiate rotation before an outage
- agents discovering an expiring credential have no approved mutation path to trigger rotation without direct operator intervention

Long-lived static secrets are the single largest practical security risk on a platform that otherwise has a strong credential posture.

## Decision

We will implement automated secret rotation for all non-ephemeral credentials using OpenBao as the rotation authority.

Rotation model:

1. **Static secrets** (e.g. PostgreSQL service passwords, SMTP credentials, Windmill API tokens) are migrated to OpenBao KV with a `rotation_period` metadata field
2. a scheduled Windmill workflow (`rotate-credentials`) runs daily, reads the KV metadata, and rotates any secret whose age exceeds `rotation_period - warning_window`
3. rotation events emit a structured NATS event (`credentials.rotated`) and a GlitchTip notice so failures are visible
4. each service role has a `tasks/rotate.yml` that applies the new credential to the running service without a full re-convergence (e.g. a Docker `exec` for a password change, or a systemd unit reload)
5. a `config/secret-catalog.json` lists every managed secret with its type, owner service, rotation period, and last-rotated timestamp (updated by the Windmill workflow)

Rotation approval:

- low-risk rotations (service-to-service passwords with no operator sessions) execute automatically
- high-risk rotations (operator API tokens, break-glass credentials) require an approval event via the command approval gate from ADR 0048 before execution

## Consequences

- Static credential age is bounded; no service account can accumulate years of implicit trust.
- Rotation failures are surfaced immediately via GlitchTip and NATS rather than discovered during an incident.
- Services must be able to reload credentials without a full restart; roles that cannot do this must be updated before rotation is enabled for them.
- The `secret-catalog.json` becomes another machine-readable contract that agents and auditors can query.

## Boundaries

- SSH certificates use step-ca's existing renewal model and are not managed by this rotation workflow.
- Dynamic database credentials from OpenBao leases do not need explicit rotation; their TTL handles it.
- Rotation of Proxmox root credentials is a break-glass procedure and is not automated.

## Implementation Notes

- The canonical secret inventory remains in [config/secret-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/secret-catalog.json), while ADR 0065 now stores its richer automation contract in the same file under `rotation_metadata` and `rotation_contracts`. That contract is validated by [scripts/secret_rotation.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/secret_rotation.py), [tests/test_secret_rotation.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/tests/test_secret_rotation.py), and the repository data-model pipeline.
- Live mutation now runs through [playbooks/secret-rotation.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/secret-rotation.yml), which dispatches to role-local apply entry points under [roles/windmill_postgres/tasks/rotate.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/windmill_postgres/tasks/rotate.yml), [roles/windmill_runtime/tasks/rotate.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/windmill_runtime/tasks/rotate.yml), and [roles/mail_platform_runtime/tasks/rotate.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/mail_platform_runtime/tasks/rotate.yml).
- [roles/openbao_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/openbao_runtime) now seeds dedicated rotatable secret paths and path-level metadata into OpenBao, while [roles/windmill_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/windmill_runtime) seeds the repo-managed `f/lv3/rotate_credentials` script as the first Windmill surface for scheduled evaluation.
- The governed execution and approval path is represented in [config/workflow-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/workflow-catalog.json), [config/command-catalog.json](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/command-catalog.json), and the operator runbook [docs/runbooks/secret-rotation-and-lifecycle.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/secret-rotation-and-lifecycle.md).
