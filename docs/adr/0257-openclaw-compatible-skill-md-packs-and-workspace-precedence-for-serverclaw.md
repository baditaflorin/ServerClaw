# ADR 0257: OpenClaw-Compatible SKILL.md Packs And Workspace Precedence For ServerClaw

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.117
- Implemented In Platform Version: 0.130.76
- Date: 2026-03-28
- Implemented On: 2026-03-31

## Context

The repository already has a governed tool registry and MCP-compatible tool
export, but that is not the same thing as a user-facing skill system. What is
missing for an OpenClaw-like product is:

- workspace-scoped packaging of assistant behavior
- clear precedence between bundled, shared, and workspace-local skills
- a compatibility story with the existing OpenClaw skill ecosystem

Without that layer, ServerClaw would have tools but no clean way to assemble or
share assistant behavior.

## Decision

ServerClaw will adopt **OpenClaw-compatible `SKILL.md` skill packs** as its
first-class skill packaging format.

### Precedence model

- workspace-local skill packs override shared skill packs
- shared skill packs override bundled skill packs
- imported third-party skill packs are never trusted automatically

### Execution model

- skill packs may reference governed tool-registry entries, n8n connector
  ports, Playwright browser-action ports, and approved memory or search ports
- skill packs do **not** grant direct shell, arbitrary network, or uncontrolled
  secret access by default

### Compatibility rule

- ServerClaw should prefer compatibility with upstream OpenClaw `SKILL.md`
  semantics where that does not weaken governance
- external skill packs must be mirrored, reviewed, and policy-gated before they
  are enabled on the platform

## Consequences

**Positive**

- ServerClaw gains an understandable, shareable assistant-extension model.
- Users can reason about skill behavior at the workspace level instead of
  treating all behavior as one giant system prompt.
- OpenClaw ecosystem reuse becomes possible without coupling the whole product
  to upstream runtime assumptions.

**Negative / Trade-offs**

- Compatibility work is required whenever upstream skill conventions evolve.
- Skill review becomes an explicit security and governance responsibility.

## Boundaries

- This ADR defines the skill-pack contract, not the full plugin marketplace.
- Compatibility does not mean unreviewed one-click import from public registries.
- The tool registry remains the governed execution surface underneath the skill
  layer.

## Related ADRs

- ADR 0069: Agent tool registry and governed tool calls
- ADR 0205: Capability contracts before product selection
- ADR 0254: ServerClaw as a distinct self-hosted agent product on LV3

## References

- <https://docs.openclaw.ai/tools/skills>
- <https://docs.openclaw.ai/tools/creating-skills>
