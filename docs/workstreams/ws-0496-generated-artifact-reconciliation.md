# WS-0496: Generated deployment-artifact reconciliation

## Goal

Repair the stale tracked generation outputs that block the governed Authentik
converge path, using only the explicitly selected 0mcp identity and topology
sources.

## Scope

- Reproduce and repair `inventory/group_vars/platform.yml` from the verified
  0mcp identity selector and committed production topology source.
- Reproduce and repair the generated HTTPS/TLS assurance rule output.
- Inspect every generated change before it is proposed for merge; do not apply
  any infrastructure change in this workstream.

## Boundary

This workstream repairs repository generation truth only. A future governed
Authentik converge remains a separate, explicitly verified live operation.

## Result

The tracked platform facts and HTTPS/TLS assurance output were already correct
when regenerated from the explicit 0mcp selectors. The false block came from
fresh worktrees lacking ignored cross-cutting inputs consumed by the platform
facts generator. Guarded preflights now materialize only those ignored inputs
before they check tracked outputs. The Authentik, GlitchTip, Outline, and
OpenBao deployment selectors all pass with the production 0mcp identity and
committed production topology inputs. The complete repository gate also
identified a stale `build/platform-manifest.json`: its recorded release date
still pointed at the previous release. Regeneration updated only that release
date and generated timestamps, and the manifest validation now passes.
The gate also identified a stale agent-coordination diagram; its regeneration
updated the branch-count indicator from 377 to 379 and passes the generated
diagram validation.
