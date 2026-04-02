# ADR 0336: Public Entrypoint Leakage Validation

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.143
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-02
- Date: 2026-04-02
- Tags: validation, public, guardrails, leakage, ci

## Context

Manual cleanup is not enough. The repo already had generators and routine edits
that could reintroduce:

- personal workstation paths
- absolute checkout paths
- deployment-specific identifiers in root onboarding docs

Without an automated guard, public-readiness drift is inevitable.

## Decision

Public entrypoints must be covered by an automated leakage validator that fails
when committed root surfaces drift back toward personal-path or
deployment-specific content.

### Initial guard scope

- committed workstation home paths are forbidden in public entrypoints
- absolute path values are forbidden in governed workstream metadata fields
- root onboarding docs must avoid deployment-specific identifiers chosen for one environment

### Integration rule

The validator must run inside the existing agent-standards gate so the repo
fails early before push or merge.

## Consequences

**Positive**

- public-readiness becomes enforceable, not aspirational
- generators and manual edits are both covered by one simple rule
- future contributors get fast feedback when a root surface stops being portable

**Negative / Trade-offs**

- some currently acceptable copy-paste shortcuts will now fail validation
- the forbidden-pattern set will need occasional tuning as the public template evolves

## Boundaries

- This ADR governs public entrypoints, not every historical document in the repo.
- This ADR does not replace secret scanning or other security validation lanes.

## Related ADRs

- ADR 0087: Repository validation gate
- ADR 0168: Automated enforcement of agent standards
- ADR 0330: Public GitHub readiness as a first-class repository lifecycle
