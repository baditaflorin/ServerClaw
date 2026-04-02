# ADR 0321: Runtime Pool Memory Envelopes And Reserved Host Headroom

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.145
- Implemented In Platform Version: not yet
- Implemented On: 2026-04-02
- Date: 2026-04-01

## Context

`docker-runtime-lv3` currently carries a broad mix of control-plane, operator,
AI, and application services on one 24 GiB runtime allocation. That makes
memory pressure both common and ambiguous:

- one service can trigger reclaim pressure for dozens of neighbors
- the capacity model can report host headroom, but the runtime tier still lacks
  a governed answer to "how much memory should these shared services get next?"
- autoscaling cannot be safe until the platform declares both pool-level limits
  and a host-side floor that must remain free

The platform needs an explicit memory increase, but it also needs a hard answer
to how far that increase is allowed to go before a new review is required.

It also needs to avoid inventing a one-off measurement stack when existing
autoscaling and metrics tooling already knows how to consume API-backed memory
signals.

## Decision

We will replace the single shared runtime memory budget with **runtime-pool
memory envelopes** backed by a reserved host free-memory floor.

### First approved production envelope

- the combined baseline memory for runtime pools must increase from the current
  single 24 GiB shared runtime toward at least **40 GiB pooled**
- the combined runtime-pool ceiling may not exceed **64 GiB pooled** without a
  new capacity review
- the Proxmox host must retain at least **20 GiB** of free or uncommitted
  memory after applying runtime-pool reservations and existing protected
  capacity classes

### Initial per-pool envelopes

- `runtime-control`: baseline 12 GiB, max 16 GiB
- `runtime-general`: baseline 12 GiB, max 20 GiB
- `runtime-ai`: baseline 16 GiB, max 28 GiB

The pool baselines are additive. The pool maxima are additive only when the
host free-memory floor still remains intact.

### Admission rule

- control-pool memory is reserved before general or AI expansion
- any requested pool resize that would violate the 20 GiB host floor must be
  rejected and escalated
- adding a new service to a runtime pool without a matching envelope update is
  considered capacity drift

### Measurement and control inputs

The preferred first implementation is:

- `Prometheus` as the canonical metrics source for pool-level memory signals
- `Nomad Autoscaler` policy checks and targets as the first reusable control
  loop for declared memory envelopes and scale boundaries

Direct custom scripts may still summarize or precompute those metrics, but they
should feed those standard surfaces rather than becoming a parallel autoscaling
stack.

## Consequences

**Positive**

- the platform gains a concrete memory increase instead of a vague intention to
  "add more RAM later"
- operators and autoscalers now share one approved set of pool bounds
- the host keeps a safety margin for Proxmox, page cache, recovery actions, and
  temporary migration work
- future agents can inspect one familiar metrics and autoscaling vocabulary
  instead of repo-specific memory heuristics

**Negative / Trade-offs**

- some currently convenient placements will stop fitting once pool ceilings are
  enforced honestly
- more memory for the runtime tier means less apparent slack elsewhere until the
  host model is rebalanced

## Boundaries

- This ADR governs pool memory envelopes and the host floor; it does not define
  the autoscaling controller logic.
- This ADR does not change the existing standby, recovery, or preview reserved
  capacity classes from ADR 0192. It must coexist with them.

## Related ADRs

- ADR 0105: Platform capacity model and resource quota enforcement
- ADR 0157: Per-VM concurrency budget and resource reservation
- ADR 0180: Standby capacity reservation and placement rules
- ADR 0192: Separate capacity classes for standby, recovery, and preview workloads
- ADR 0232: Nomad for durable batch and long-running internal jobs
