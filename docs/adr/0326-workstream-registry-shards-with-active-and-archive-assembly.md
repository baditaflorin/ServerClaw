# ADR 0326: Workstream Registry Shards With Active And Archive Assembly

- Status: Accepted
- Implementation Status: Implemented on workstream branch
- Implemented In Repo Version: not yet
- Implemented In Platform Version: N/A
- Implemented On: 2026-04-03
- Date: 2026-04-01
- Tags: workstreams, registry, archive, sharding, coordination

## Context

`workstreams.yaml` has become a long-lived operational ledger for every active,
merged, and live-applied branch. That gave the repo one easy place to look, but
the file now mixes three different concerns:

- active coordination for work in flight
- historical audit records for finished workstreams
- release metadata consumed during integration

As the number of completed workstreams grows, the single file becomes harder to
review and more expensive for agents to read just to find the current active set.

## Decision

We will split workstream metadata into **per-workstream shards** and keep a
generated compatibility assembly for existing readers.

### Source layout

Workstream metadata will move toward:

```text
workstreams/
  active/<workstream-id>.yaml
  archive/<year>/<workstream-id>.yaml
```

Each workstream shard carries the metadata currently embedded in the registry:
branch, status, ownership manifest, shared surfaces, release metadata, and
blockers.

### Lifecycle rule

- active workstreams live under `workstreams/active/`
- once a workstream reaches a terminal state and any repo-version bookkeeping is
  complete, its shard moves to `workstreams/archive/<year>/`
- archived workstreams stop cluttering the active coordination surface, but
  remain first-class repo history

### Generated compatibility surface

`workstreams.yaml` remains as a generated compatibility artifact containing:

- delivery and release policy blocks
- the currently active workstreams
- a compact summary of archived counts or pointers

Existing tools can keep reading `workstreams.yaml` until they are upgraded to
load the shard directories directly.

## Consequences

**Positive**

- active coordination becomes much smaller and easier to inspect
- one workstream can change its own metadata without rebasing the full history
- archive growth stops inflating the default onboarding surface forever
- release automation can operate on structured per-workstream files

**Negative / Trade-offs**

- generators must preserve stable ordering and compatibility for current callers
- archive movement introduces another lifecycle transition to validate
- some grep-based workflows will need new helper commands or docs

## Boundaries

- This ADR does not replace `docs/workstreams/*.md`; those remain the narrative
  handoff documents.
- This ADR does not change the protected release files listed in AGENTS.md.
- The top-level policy metadata may remain hand-authored if that is simpler than
  fully generating it.

## Related ADRs

- ADR 0167: Agent handoff and context preservation
- ADR 0173: Workstream surface ownership manifest
- ADR 0174: Integration-only canonical truth assembly
- ADR 0182: Live apply merge train and rollback bundle
