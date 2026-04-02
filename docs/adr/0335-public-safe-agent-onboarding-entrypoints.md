# ADR 0335: Public-Safe Agent Onboarding Entrypoints

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.143
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-02
- Date: 2026-04-02
- Tags: onboarding, agents, docs, public, entrypoints

## Context

The fastest way for any agent or collaborator to understand the repo is to read
the root entrypoints:

- `README.md`
- `AGENTS.md`
- `.repo-structure.yaml`
- `.config-locations.yaml`

Those files were doing too much. They mixed general workflow rules with one
deployment's provider, hostnames, IPs, and operator assumptions.

## Decision

Root onboarding entrypoints must stay public-safe and generic, focusing on repo
navigation, workflow, and replaceable patterns rather than one deployment's
live identifiers.

### Root-entrypoint rule

- explain how the repo is organized
- explain how a fork should start
- explain where deployment-specific facts belong
- avoid concrete provider, hostname, IP, and domain values unless the value is intentionally an example

## Consequences

**Positive**

- new agents can onboard quickly without inheriting private context
- forks get a cleaner first-read experience
- root docs become stable public documentation rather than live deployment notes

**Negative / Trade-offs**

- operators may need to follow links into deeper runtime truth for environment-specific details

## Boundaries

- This ADR governs root onboarding surfaces, not every historical runbook or receipt.
- This ADR does not prohibit deeper deployment-specific truth where it is intentionally maintained.

## Related ADRs

- ADR 0163: Repository structure index for agent discovery
- ADR 0166: Canonical configuration locations registry
- ADR 0327: Sectional agent discovery registries and generated onboarding packs
- ADR 0330: Public GitHub readiness as a first-class repository lifecycle
