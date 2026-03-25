# ADR 0160: Parallel Dry-Run Fan-Out for Intent Batch Validation

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.145.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Date: 2026-03-24

## Context

When an agent or operator submits multiple intents in sequence — a batch of related changes, or the observation loop's (ADR 0126) response to multiple simultaneous findings — each intent currently goes through the validation pipeline serially:

1. Compile intent N.
2. Run dry-run (check mode).
3. Evaluate dry-run diff output.
4. Pass conflict detection.
5. Queue or execute.
6. Wait for completion.
7. Repeat for intent N+1.

In a scenario where 5 intents are queued (e.g., the observation loop detected drift on 5 services simultaneously), the serial pipeline means each intent waits for all previous ones to complete dry-run before it even begins validation. If each dry-run takes 60 seconds, the batch takes 300 seconds just to validate — before any actual execution has started.

The insight is that **dry-runs are read-only operations**. A dry-run (Ansible `--check --diff`, or a Docker Compose config diff) does not modify the system; it only reads current state and computes what would change. Multiple dry-runs can execute simultaneously without conflict (they all read the same state), and their outputs can be evaluated in parallel.

By **fanning out dry-runs for all intents in a batch simultaneously**, the total dry-run time is `max(individual_dry_run_times)` instead of `sum(individual_dry_run_times)` — a significant speedup for batches of 3 or more intents.

After fan-out dry-runs complete, conflict detection runs on the **combined output** of all dry-runs simultaneously, not sequentially. This can detect cross-intent conflicts that serial dry-runs miss:

> Example: Intent A changes NetBox's `REDIS_PASSWORD` in its config and intent B restarts the Redis container. Serial validation would not catch the race: A's dry-run shows a file change (fine), B's dry-run shows a restart (fine). But in reality, B's restart during A's config apply causes a window where NetBox has the new config but Redis is restarting, causing a brief service outage. The **combined output** of A and B reveals the dependency, allowing conflict detection to flag it.

## Decision

We implement a controller-local **parallel dry-run fan-out** for multi-intent batches: all semantic dry-runs in a batch execute concurrently, cross-intent conflict analysis runs on the combined result set, and the platform emits a staged execution plan before any batch is submitted for mutation.

## Implementation Notes

Repository implementation landed in `0.145.0` with the following surfaces:

- `GoalCompiler.compile_batch()` in [platform/goal_compiler/compiler.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/goal_compiler/compiler.py)
- `IntentBatchPlanner` and the batch plan dataclasses in [platform/goal_compiler/batch.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/goal_compiler/batch.py)
- operator preview in [scripts/lv3_cli.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/lv3_cli.py)
- batch-plan ledger event registration in [config/ledger-event-types.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/ledger-event-types.yaml)

### Batch compilation

`GoalCompiler.compile_batch()` compiles a list of instructions into a single `CompiledIntentBatch`. Each instruction still uses the normal single-intent compiler path, including scope binding, health gating, resource-claim inference, and actor-policy enforcement.

### Fan-out execution

`IntentBatchPlanner.plan()` fans out semantic diff computation with a bounded thread pool. The current repository implementation uses the existing ADR 0120 diff engine directly rather than a Windmill `forloop_parallel` flow, which keeps the batch validator aligned with the current controller-local intent tooling.

If one dry-run fails, that intent is marked rejected with a `dry_run_failed` reason while the rest of the batch still receives a plan.

### Combined diff and conflict classification

The planner merges two evidence sources per intent:

- declared `resource_claims`
- `SemanticDiff.changed_objects`

This combined touch map is then classified into the currently implemented outcomes:

| Cross-intent touch pattern | Classification | Action |
|---|---|---|
| two intents write the same resource | `write_write_conflict` | reject the later intent in submitted order |
| one intent writes a resource that another only reads | `read_after_write_dependency` | order writer before reader |
| one intent restarts a resource while another mutates it | `restart_during_config` | order config change before restart |

### Execution plan generation

The planner converts the dependency set into ordered `ExecutionStage` rows. Independent intents share the same `parallelism: full` stage; dependent intents become later sequential stages with `wait_for_stage` references. The resulting plan is recorded as `intent.batch_plan` when a ledger sink is configured.

### CLI surface

`lv3 intent batch --instruction ... --instruction ...` now provides an operator-facing preview of:

- dry-run failures
- cross-intent conflict classification
- staged execution order
- rejected intents and reasons

### Performance comparison

| Scenario | Serial validation | Fan-out validation |
|---|---|---|
| 5 intents × 60s dry-run | 300s to validate | 60s to validate (all parallel) |
| 3 independent intents | 180s + 180s execute | 60s + 60s execute (parallel) |
| 3 intents with one dependency | 180s + 120s execute | 60s + 90s execute (staged) |

## Consequences

**Positive**

- Batch dry-run time is `max(individual_dry_run_times)` rather than `sum(...)`. For the observation loop's typical batch of 3–5 concurrent findings, this is a 3–5× speedup in the validation phase.
- Cross-intent conflict detection on the combined diff catches ordering dependencies that serial validation misses entirely. The platform is safer as well as faster.
- The execution plan provides a dependency graph that operators can review (in the ops portal) before the batch executes, giving them confidence in what is about to run.

**Negative / Trade-offs**

- Parallel dry-runs consume concurrency budget (ADR 0157) on the target VMs simultaneously. For large batches targeting the same VM, the fan-out may need throttling (hence `max_parallelism: 5`).
- The combined diff and conflict detection logic is complex. A bug in cross-intent dependency classification could either over-block (too many `read_after_write_dependency` classifications causing unnecessary serialisation) or under-block (missing `write_write_conflict` classifications causing data corruption).
- The first implementation is controller-local. The batch plan is not yet dispatched through ADR 0155's queue or rendered in the ops portal.

## Boundaries

- Fan-out validation is triggered by `compile_batch()` / `validate_batch()` and the CLI preview surface. Single-intent compilation remains unchanged.
- `intent.batch_plan` is currently a planning event, not a scheduler submission. Stage-by-stage execution by ADR 0155 remains follow-up work.
- No platform live-apply claim is made for this release; `Implemented In Platform Version` remains `not yet`.

## Related ADRs

- ADR 0112: Deterministic goal compiler (batch compilation entry point)
- ADR 0115: Event-sourced mutation ledger (intent.batch_plan event)
- ADR 0120: Dry-run semantic diff engine (individual dry-runs that are fanned out)
- ADR 0126: Observation-to-action closure loop (future batch caller)
- ADR 0127: Intent deduplication and conflict resolution (resource-claim input reused during batch planning)
- ADR 0154: VM-scoped execution lanes (future execution consumer of staged plans)
- ADR 0155: Intent queue (future stage-by-stage dispatcher for planned batches)
- ADR 0157: Per-VM concurrency budget (fan-out respects max_parallelism budget)
