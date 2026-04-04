# ADR 0339: Reference Deployment Samples And Replaceable Provider Profiles

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-04
- Date: 2026-04-02
- Tags: samples, templates, provider, onboarding, replication

## Context

A public repo becomes genuinely forkable only when a new operator can answer
three questions quickly:

1. Which files are canonical examples?
2. Which values must be replaced for my environment?
3. What is the simplest path from clone to first successful dry run?

Current repo structure and ADRs already contain the raw ingredients, but that
journey is still optimized for an existing deployment rather than a first-time
fork.

## Decision

We will provide reference deployment samples and replaceable provider profiles
as the default onboarding flow for new forks.

### Sample flow

- start from example inventory and publication profiles
- copy or render local overlays for secrets and operator-local artefacts
- run validation before the first live mutation
- progressively replace examples with real provider, host, and publication values

### Replaceability rule

Provider choices, publication hostnames, and local path assumptions should be
expressed as replaceable profiles wherever practical, not as hidden constants.

## Consequences

**Positive**

- the repo becomes easier to replicate and teach
- onboarding becomes a guided flow instead of a reverse-engineering exercise
- future providers or topologies can reuse the same repository contracts

**Negative / Trade-offs**

- sample profiles will require maintenance as the real automation evolves
- some current catalogs may need companion examples or profile abstractions

## Boundaries

- This ADR does not require a provider-neutral implementation everywhere immediately.
- This ADR does not replace the need for operator judgment on live topology choices.

## Related ADRs

- ADR 0207: Anti-corruption layers at provider boundaries
- ADR 0327: Sectional agent discovery registries and generated onboarding packs
- ADR 0334: Example-first inventory and service identity catalogs
