# ADR 0202: Excalidraw Auto Generated Architecture Diagrams

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.16
- Implemented In Platform Version: 0.130.31
- Implemented On: 2026-03-27
- Date: 2026-03-27

## Context

The platform already keeps its canonical infrastructure truth in versioned
catalogs, generated docs, and machine-readable inventories, but architecture
diagrams still lag behind because they are usually drawn by hand after the fact.

That creates two recurring problems:

- visual architecture references drift away from the repo truth
- operators do not have a private, repo-managed place to inspect and collaborate on those diagrams

The target phase of the platform is already past bootstrap. The next useful
documentation surface is a private diagramming tool that can render current
platform structure from repo-managed data and can still support interactive
editing when operators need to annotate or iterate on a design.

## Decision

We will add a repo-managed Excalidraw publication at `draw.example.com` and commit a
generated set of `.excalidraw` architecture scenes under `docs/diagrams/`.

### Runtime model

- The Excalidraw frontend runs on `docker-runtime`.
- The official collaboration room runs beside it on a separate local port.
- The shared NGINX edge publishes `draw.example.com` behind the existing
  oauth2-proxy gate.
- The edge routes `/socket.io/` to the collaboration room while routing all
  other requests to the frontend.

### Generation model

- `scripts/generate_diagrams.py` is the canonical generator for the committed
  scene files.
- The generator derives diagrams from repo-managed platform inputs such as host
  vars, dependency graph data, and the workstream registry.
- Generated scene files are committed artifacts and must be refreshed through the
  generator, not edited by hand.

### Operator workflow

- Use `make converge-excalidraw` to converge the runtime and edge publication.
- Use `python scripts/generate_diagrams.py --write` to refresh the committed
  scenes.
- Use `lv3 diagram open <name>` to open a committed diagram source locally.

## Consequences

**Positive**

- Architecture diagrams gain the same regeneration discipline as other repo
  artifacts.
- Operators get a private collaboration surface for architecture review and
  incident annotation.
- Shared-edge authentication keeps the diagram surface consistent with other
  operator-only portals.

**Negative / Trade-offs**

- The stock Excalidraw frontend image needs a deterministic startup patch so the
  collaboration origin points to the private deployment instead of the public
  default.
- The shared edge needs path-based upstream routing for the collaboration socket
  path, which slightly increases publication template complexity.

## Boundaries

- This ADR governs the private Excalidraw runtime and generated source scenes,
  not exported PNG or SVG publication.
- This ADR does not make architecture diagrams part of the public docs portal.
- This ADR does not introduce a new standalone identity system for Excalidraw;
  the shared edge auth model remains authoritative.

## Related ADRs

- ADR 0038: Generated status documents from canonical state
- ADR 0075: Service capability catalog
- ADR 0094: Developer portal
- ADR 0133: Portal authentication by default
- ADR 0136: HTTP security headers hardening
- ADR 0165: Playbook / role metadata standard
- ADR 0167: Agent handoff and context preservation
