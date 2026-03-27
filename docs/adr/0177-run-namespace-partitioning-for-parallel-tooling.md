# ADR 0177: Run Namespace Partitioning for Parallel Tooling

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.2
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-27
- Date: 2026-03-26

## Context

Even when repository ownership and runtime locking are correct, parallel execution still fails if the underlying tools share local scratch paths. Typical collisions include:

- Ansible temp directories and retry files
- OpenTofu plan files and cached state
- generated inventories
- build artifacts and rendered templates
- local logs and receipts written to predictable filenames

ADR 0156 isolates platform session workspaces conceptually, but infra tooling in this repository also needs a uniform local-on-disk namespace convention.

## Decision

We will require every mutable execution path to run inside a **run namespace** identified by `run_id`.

### Namespace root

All ephemeral execution artifacts live below:

```text
.local/runs/<run_id>/
```

Expected subpaths:

- `.local/runs/<run_id>/ansible/`
- `.local/runs/<run_id>/tofu/`
- `.local/runs/<run_id>/rendered/`
- `.local/runs/<run_id>/logs/`
- `.local/runs/<run_id>/receipts/`

### Tooling rules

- Ansible uses namespace-specific temp, inventory render, and log paths
- OpenTofu writes plan outputs per `run_id` and must not reuse another workstream's local cache directly
- generated files are promoted into canonical paths only by an explicit publish step

### Publish boundary

Artifacts produced inside a run namespace are disposable until promoted. A run may fail, be retried, or be discarded without polluting shared paths.

## Implementation Notes

Repository implementation landed in `0.177.2`.

- `scripts/run_namespace.py` resolves canonical `.local/runs/<run_id>/...` paths and can pre-create the namespace tree.
- `scripts/run_with_namespace.sh`, `Makefile`, and `scripts/tofu_exec.sh` now route mutable Ansible and OpenTofu execution through per-run temp, plan, log, and runtime paths.
- `scripts/remote_exec.sh`, the diff-engine adapters, and `scripts/drift_detector.py` forward and consume `LV3_RUN_ID` so nested and parallel tooling stays namespaced.
- focused regression coverage verifies namespaced drift/diff behavior, remote forwarding, and concurrent OpenTofu adapter isolation.

## Consequences

**Positive**

- Multiple agents can run tooling at once from separate worktrees without temp-file collisions.
- Debugging gets easier because each run has a self-contained artifact bundle.
- Promotion into shared paths becomes explicit.

**Negative / Trade-offs**

- Local disk usage increases until old run namespaces are cleaned.
- Existing scripts need to accept `run_id` and derived paths.

## Boundaries

- Namespace partitioning complements but does not replace git worktrees.
- Canonical repository files are still shared and must obey ownership and contract rules.

## Related ADRs

- ADR 0085: OpenTofu IaC for VM lifecycle management
- ADR 0156: Agent session workspace isolation
- ADR 0173: Workstream surface ownership manifest
