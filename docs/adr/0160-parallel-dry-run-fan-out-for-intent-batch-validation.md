# ADR 0160: Parallel Dry-Run Fan-Out for Intent Batch Validation

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
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

We will implement a **parallel dry-run fan-out** for multi-intent batches: all dry-runs in a batch execute in parallel, and conflict detection operates on the combined result set before any execution begins.

### Batch compilation

The goal compiler (ADR 0112) is extended with a `compile_batch()` method:

```python
# platform/compiler/goal_compiler.py

def compile_batch(
    self,
    instructions: list[str],
    actor_id: str,
    context_id: UUID,
    batch_id: UUID = None,
) -> IntentBatch:
    """
    Compile multiple instructions into an IntentBatch.
    Each intent is compiled independently; cross-intent dependencies are
    analysed during the fan-out dry-run phase.
    """
    if batch_id is None:
        batch_id = uuid4()

    intents = [
        self.compile(instr, actor_id, context_id, skip_dry_run=True)
        for instr in instructions
    ]

    return IntentBatch(
        batch_id=batch_id,
        intents=intents,
        context_id=context_id,
        actor_id=actor_id,
        submitted_at=now(),
    )
```

`skip_dry_run=True` defers the individual dry-run; it will run as part of the fan-out.

### Fan-out dry-run execution

The batch validation workflow `validate-intent-batch` executes all dry-runs in parallel using Windmill's parallel step execution:

```python
# config/windmill/flows/validate-intent-batch.yaml (Windmill flow definition)

flow:
  name: validate-intent-batch
  steps:
    - id: fan_out_dry_runs
      type: forloop_parallel        # Windmill parallel loop
      items: "{{ batch.intents }}"
      max_parallelism: 5            # At most 5 concurrent dry-runs
      step:
        id: dry_run
        type: script
        path: f/platform/intent/dry_run_single_intent
        args:
          intent_id: "{{ item.intent_id }}"
          workspace_schema: "{{ batch.workspace_schema }}"  # Isolated per-intent (ADR 0156)

    - id: combine_diff_outputs
      type: script
      path: f/platform/intent/combine_diff_outputs
      args:
        batch_id: "{{ batch.batch_id }}"
        dry_run_results: "{{ steps.fan_out_dry_runs.results }}"

    - id: cross_intent_conflict_detection
      type: script
      path: f/platform/intent/cross_intent_conflict_check
      args:
        combined_diff: "{{ steps.combine_diff_outputs.result }}"
        intents: "{{ batch.intents }}"

    - id: generate_execution_plan
      type: script
      path: f/platform/intent/generate_execution_plan
      args:
        conflict_report: "{{ steps.cross_intent_conflict_detection.result }}"
        intents: "{{ batch.intents }}"
        batch_id: "{{ batch.batch_id }}"
```

### Combined diff and cross-intent conflict detection

The `combine_diff_outputs` step merges the diff outputs from all individual dry-runs into a unified change set:

```python
# config/windmill/scripts/combine-diff-outputs.py

def combine_diff_outputs(batch_id: UUID, dry_run_results: list[DryRunResult]) -> CombinedDiff:
    """
    Merge all individual dry-run diffs into a unified change set.
    Tracks which intent "owns" each change.
    """
    file_changes = defaultdict(list)   # {file_path: [(intent_id, change)]}
    service_restarts = defaultdict(list)
    config_writes = defaultdict(list)

    for result in dry_run_results:
        for change in result.file_changes:
            file_changes[change.path].append((result.intent_id, change))
        for restart in result.service_restarts:
            service_restarts[restart.service_id].append((result.intent_id, restart))
        for write in result.config_writes:
            config_writes[write.target].append((result.intent_id, write))

    # Flag any resource touched by more than one intent
    cross_intent_touches = {
        path: intents
        for path, intents in file_changes.items()
        if len(set(i for i, _ in intents)) > 1
    }

    return CombinedDiff(
        file_changes=file_changes,
        service_restarts=service_restarts,
        config_writes=config_writes,
        cross_intent_touches=cross_intent_touches,
    )
```

The `cross_intent_conflict_check` step classifies cross-intent touches:

| Cross-intent touch pattern | Classification | Action |
|---|---|---|
| Two intents write the same file | `write_write_conflict` | Reject lower-priority intent; re-queue |
| Intent A writes file; Intent B reads same file after A's write | `read_after_write_dependency` | Order: A must complete before B starts |
| Intent A restarts service X; Intent B writes X's config | `restart_during_config` | Order: B must complete before A starts |
| Two intents restart different services, no shared files | `safe_parallel` | Execute in parallel |

### Execution plan generation

From the conflict analysis, the `generate_execution_plan` step produces an ordered, parallelism-aware execution plan:

```python
# Output of generate_execution_plan:
execution_plan = ExecutionPlan(
    batch_id=batch_id,
    stages=[
        ExecutionStage(
            stage_id=1,
            intents=["intent-A", "intent-C"],  # No dependencies between these two
            parallelism="full",
        ),
        ExecutionStage(
            stage_id=2,
            intents=["intent-B"],              # Depends on stage 1 completing first
            parallelism="sequential",
            wait_for_stage=1,
        ),
        ExecutionStage(
            stage_id=3,
            intents=["intent-D", "intent-E"],  # Can run after stage 2
            parallelism="full",
        ),
    ],
    rejected_intents=["intent-F"],             # write_write_conflict with intent-A
    rejected_reasons={"intent-F": "write_write_conflict on /etc/netbox/config.py"},
)
```

The execution plan is committed to the mutation ledger (ADR 0115) as `intent.batch_plan` event and executed by the intent queue dispatcher (ADR 0155) using stage-aware scheduling.

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
- Windmill's parallel loop (`forloop_parallel`) has a different execution model from sequential steps. Error handling in a parallel loop requires careful design: if 3 of 5 dry-runs succeed and 2 fail, the batch should report the failures and execute the 3 successful intents, not abort the whole batch.

## Boundaries

- Fan-out validation is triggered by the `compile_batch()` API. Single-intent compilations continue to use the sequential (compile → dry-run → check → execute) pipeline.
- The execution plan is advisory for cross-VM operations; within a single VM, the execution plan ordering is enforced by lane scheduling (ADR 0154).

## Related ADRs

- ADR 0044: Windmill (parallel loop execution in the fan-out flow)
- ADR 0112: Deterministic goal compiler (compile_batch() API; skip_dry_run flag)
- ADR 0115: Event-sourced mutation ledger (intent.batch_plan event)
- ADR 0120: Dry-run semantic diff engine (individual dry-runs that are fanned out)
- ADR 0126: Observation-to-action closure loop (multiple simultaneous findings trigger compile_batch)
- ADR 0154: VM-scoped execution lanes (execution plan staged per lane)
- ADR 0155: Intent queue (execution plan stages dispatched stage-by-stage)
- ADR 0156: Agent session workspace isolation (each dry-run gets workspace-scoped scratch space)
- ADR 0157: Per-VM concurrency budget (fan-out respects max_parallelism budget)
