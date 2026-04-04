# ADR 0327: Sectional Agent Discovery Registries And Generated Onboarding Packs

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.4
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-03
- Date: 2026-04-01
- Tags: agent-discovery, onboarding, registries, config, sharding

## Context

The repository deliberately invested in two onboarding surfaces:

- `.repo-structure.yaml`
- `.config-locations.yaml`

That helped agents stop wandering the tree, but success created a new scaling
problem. Both files keep growing because every new domain, service, and config
surface gets summarized there.

A single-file onboarding story no longer scales cleanly:

- the files are large enough that quick reads become expensive
- unrelated changes collide in the same registry
- some sections matter only to one concern, but every agent pays to read all of them

## Decision

We will reorganize discovery metadata into **sectional registries** with
generated root entrypoints and optional onboarding packs.

### Sectional registry layout

The detailed sources will be grouped by concern, for example:

```text
docs/discovery/repo-structure/
  governance.yaml
  automation.yaml
  services.yaml

docs/discovery/config-locations/
  platform.yaml
  security.yaml
  observability.yaml
```

Each section file owns one coherent domain instead of one giant mixed registry.

### Generated root entrypoints

The top-level files remain because AGENTS.md points new agents to them:

- `.repo-structure.yaml`
- `.config-locations.yaml`

Those files become concise generated entrypoints with:

- high-level quick-start guidance
- short summaries of each section
- pointers to the deeper sectional files

### Onboarding packs

Tooling may also generate small concern-specific onboarding packs, such as:

- `build/onboarding/agent-core.yaml`
- `build/onboarding/automation.yaml`
- `build/onboarding/service-catalog.yaml`

Agents or helper scripts can request the pack that matches the task instead of
loading every registry section by default.

## Consequences

**Positive**

- onboarding reads stay small enough to remain practical
- registry ownership becomes clearer by concern
- discovery updates can land without rebasing unrelated sections
- future automation can assemble task-specific onboarding payloads

**Negative / Trade-offs**

- the generation contract must stay trustworthy or onboarding will fragment
- AGENTS.md and validation rules must preserve the root-entrypoint guarantee
- some humans may initially prefer one giant file until the new navigation
  helpers are in place

## Boundaries

- This ADR does not remove the top-level discovery files.
- This ADR does not decide the exact pack-selection UX for agents or scripts.
- Generated onboarding packs are convenience artifacts, not new canonical truth.

## Related ADRs

- ADR 0038: Generated status documents from canonical state
- ADR 0163: Repository structure index for agent discovery
- ADR 0166: Canonical configuration locations registry
- ADR 0168: Automated enforcement of agent standards
