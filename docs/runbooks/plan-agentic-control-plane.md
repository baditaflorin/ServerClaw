# Agentic Control-Plane Roadmap

## Purpose

This runbook ties the next control-plane ADR set into one operating model for:

- secure commands
- email send
- API access
- agent and operator workflows

## Result

When the proposed ADRs are implemented together, the recommended communication paths become:

1. secure commands
   - operator or agent reaches the host over Tailscale or the private network
   - SSH trust is based on short-lived credentials from `step-ca`
   - routine command execution lands on `ops`, not `root`
   - recurring mutations are represented as named command contracts
2. email send
   - the internal mail platform from ADR 0041 is the single submission path
   - sender identities are separated into notification profiles
   - agents and applications do not reuse one generic SMTP login
3. API access
   - private APIs default to internal-only publication
   - internal credentials come from OpenBao or short-lived certificates
   - operator and agent automation can use Windmill for scheduled or event-driven execution instead of raw shell access

## Proposed ADR Map

- [ADR 0042](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0042-step-ca-for-ssh-and-internal-tls.md): internal CA for SSH and internal TLS
- [ADR 0043](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0043-openbao-for-secrets-transit-and-dynamic-credentials.md): secret authority for tokens, transit, and dynamic credentials
- [ADR 0044](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0044-windmill-for-agent-and-operator-workflows.md): workflow runtime for agent and operator jobs
- [ADR 0045](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0045-control-plane-communication-lanes.md): communication lanes for command, API, message, and event traffic
- [ADR 0046](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0046-identity-classes-for-humans-services-and-agents.md): identity taxonomy for humans, services, agents, and break-glass users
- [ADR 0047](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0047-short-lived-credentials-and-internal-mtls.md): short-lived credential policy
- [ADR 0048](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0048-command-catalog-and-approval-gates.md): safe execution contracts for remote mutation
- [ADR 0049](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0049-private-first-api-publication-model.md): API publication policy
- [ADR 0050](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0050-transactional-email-and-notification-profiles.md): governed sender profiles on top of ADR 0041
- [ADR 0051](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/adr/0051-control-plane-backup-recovery-and-break-glass.md): recovery policy for the control plane

## Recommended Rollout Order

1. identity taxonomy and communication lanes
   - adopt ADR 0045 and ADR 0046 first so new app work has clear boundaries
2. trust and secrets
   - implement ADR 0042 and ADR 0043 before expanding agent access
3. credential policy
   - implement ADR 0047 so new services default to short-lived credentials
4. workflow runtime
   - implement ADR 0044 once secrets and identities exist
5. command safety
   - implement ADR 0048 before giving agents broader mutation powers
6. API publication and mail profiles
   - implement ADR 0049 and ADR 0050 as services are exposed
7. recovery
   - implement ADR 0051 before treating the new control plane as durable

## Placement Guidance

For the current single-node-first topology, the pragmatic initial placement is:

- `docker-runtime-lv3` for `step-ca`, OpenBao, and Windmill
- `postgres-lv3` for Windmill database state
- the existing mail runtime defined by ADR 0041 for SMTP and mail API work

This keeps the first implementation consistent with the existing runtime boundary. If the control-plane blast radius becomes too wide later, these components can move to a dedicated security or control-plane VM in a follow-up ADR.

## Verification Targets

Future implementation work should be considered successful only when:

- operator SSH can use short-lived credentials instead of relying on copied static keys
- an agent can execute an approved routine workflow without direct root access
- internal APIs are classified and not accidentally public
- mail send works through documented sender profiles
- restore guidance exists for the new control-plane components
