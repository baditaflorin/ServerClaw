# ADR 0352: Token-Budgeted Agent Onboarding Packs

- Status: Accepted
- Implementation Status: Not Implemented
- Date: 2026-04-05
- Tags: llm, token-budget, agent-discovery, onboarding, performance

## Context

The current agent onboarding system (ADR 0327, ADR 0335) generates three
general-purpose packs in `build/onboarding/`:

| File | Size | Approx tokens |
|---|---|---|
| `agent-core.yaml` | 19.3 KB | ~5,000 |
| `automation.yaml` | 43.5 KB | ~11,000 |
| `service-catalog.yaml` | 60.1 KB | ~15,000 |

An agent performing a focused task — say, restarting the Keycloak service —
currently receives the full `service-catalog.yaml` (15,000 tokens) to locate
the 300 tokens of Keycloak-specific information it actually needs.

With tens of agents running in parallel, each paying the full onboarding
cost multiplies total token expenditure by 50–100×. At current LLM API
pricing this is significant. For local Ollama inference it degrades throughput.

ADR 0348 introduces per-service `service.llm.yaml` files (≤500 tokens each).
This ADR defines how those files are assembled into **task-scoped onboarding
packs** with enforced token budgets.

The existing `docs/discovery/onboarding-packs.yaml` defines pack types but
does not enforce token budgets or generate dynamically scoped packs.

## Decision

### 1. Onboarding pack taxonomy

Three categories of pack, each with a hard token budget:

| Pack category | Budget | When to use |
|---|---|---|
| **nano** | ≤ 1,000 tokens | Single-service read-only check or status query |
| **micro** | ≤ 4,000 tokens | Single-service apply or config change |
| **standard** | ≤ 12,000 tokens | Multi-service apply or cross-cutting operation |

Agents declare their required pack category in their capability manifest
(ADR 0349) field `onboarding_pack_category`. Default: `micro`.

The full 15,000-token catalog is reserved for catalog-generation tooling and
is explicitly prohibited for task-scoped agents.

### 2. Pack composition algorithm

`scripts/generate_onboarding_pack.py` (updated):

```
generate_onboarding_pack.py \
  --task apply-service \
  --service keycloak \
  --category micro \
  --out build/onboarding/packs/micro-keycloak.yaml
```

The algorithm:

1. Load `roles/<service_role>/service.llm.yaml` (≤500 tokens) — primary.
2. Load `service.llm.yaml` for each `depends_on` (depth 1) — dependencies.
3. Load `build/onboarding/agent-core.yaml` sections relevant to the task type,
   filtered to declared playbooks only.
4. Append repo-level meta: `VERSION`, current `workstreams.yaml` active entries,
   relevant ADR summaries (from `.index.yaml`).
5. If total > budget: drop dependency details (keep names only), drop ADR
   summaries, drop non-essential agent-core sections, in that priority order.
6. Write pack with token count in header.

```yaml
# build/onboarding/packs/micro-keycloak.yaml
# GENERATED — do not edit by hand
# Pack: micro | Service: keycloak | Budget: 4000 tokens | Actual: 2847 tokens
# Generated: 2026-04-05T10:00:00Z
---
service: { ...keycloak service.llm.yaml content... }
dependencies:
  postgres_ha: { name: postgres_ha, description: "HA Postgres cluster", port: 5432 }
  step_ca: { name: step_ca, description: "Internal CA for TLS", port: 9000 }
  openbao: { name: openbao, description: "Secret store", port: 8200 }
platform:
  version: "0.178.3"
  active_workstreams: ["ws-0346", "ws-0348"]
agent_core:
  apply_protocol: "..."   # filtered excerpt
adrs:
  - { number: "0022", summary: "Keycloak as platform IdP" }
  - { number: "0085", summary: "IaC Boundary" }
```

### 3. Pack caching and invalidation

Generated packs are cached in `build/onboarding/packs/` with a cache key
based on:
- Service `service.llm.yaml` mtime
- `agent-core.yaml` mtime
- `VERSION` value

A pack is stale if any input file is newer than the pack. The `Makefile`
target `packs` regenerates all stale packs. CI runs `make packs --dry-run`
to detect drift.

### 4. Agent loading protocol (mandatory)

Agents must load packs using the following precedence:

1. Check for a pre-generated pack matching `(task_type, service, category)`.
2. If found and fresh: load it directly.
3. If not found or stale: call `generate_onboarding_pack.py` at runtime and
   cache the result.
4. Never load `service-catalog.yaml` directly for single-service tasks.

The `AGENTS.md` working rules are updated to add: *"Always load the
smallest applicable onboarding pack. Loading service-catalog.yaml for a
single-service task is a policy violation and will be flagged in the
mutation audit log."*

### 5. Token budget enforcement in tests

`tests/test_onboarding_packs.py`:
- Assert all packs in `build/onboarding/packs/` have `Actual:` token count in header.
- Assert nano packs ≤ 1,000, micro ≤ 4,000, standard ≤ 12,000.
- Token counting uses `tiktoken` with `cl100k_base` encoding (used by GPT-4
  and Claude API). Other encoders may count differently; the limit is
  conservative.

### 6. Nano pack use case

Nano packs (≤1,000 tokens) are designed for LLM agents that only need to
answer: "Is service X healthy? What is its health endpoint?" They contain:
- `service.llm.yaml` `health_check`, `port`, `vmid`, `description` only.
- Current `platform_manifest.json` entry for the service (filtered).
- No dependency context.

Generated as: `build/onboarding/packs/nano-<service>.yaml`.

## Places That Need to Change

### `scripts/generate_onboarding_pack.py`

Full rewrite from the current general-purpose generator. New signature and
algorithm as defined above. Add `--category` and `--service` flags.

### `Makefile`

Add `packs` target that regenerates all stale packs. Add `check-packs` target
(dry-run diff, used in CI).

### `AGENTS.md`

Update onboarding section: mandate pack category declaration, prohibit
direct catalog loading for single-service tasks.

### `config/agent-policies.yaml`

Add `max_onboarding_pack_category` per agent role. E.g., observability agents
are capped at `micro`; apply agents may use `standard`.

### `tests/test_onboarding_packs.py` (new)

Token budget enforcement tests as described.

### `docs/runbooks/agent-onboarding-packs.md` (new)

Describes pack categories, how to generate, how to debug budget overruns.

## Consequences

### Positive

- Token cost per agent drops from ~31,000 (full catalog + core) to 1,000–4,000
  for typical single-service tasks. 8–30× reduction.
- Local Ollama inference becomes viable for micro-level agent tasks —
  within context window limits of small models.
- Pre-generated packs enable agents to start with zero generation latency.

### Negative / Trade-offs

- Pack generation adds a CI step and cache invalidation complexity.
- Token counting with `tiktoken` is an approximation for non-OpenAI models.
  Anthropic and Ollama models may count differently; actual context use
  may exceed the declared budget.
- Stale packs: if a service's `service.llm.yaml` changes and packs are not
  regenerated before an agent run, the agent operates on stale context.

## Related ADRs

- ADR 0327: Sectional Agent Discovery Registries and Generated Onboarding Packs
- ADR 0335: Public-Safe Agent Onboarding Entrypoints
- ADR 0344: Single-Source Environment Topology
- ADR 0348: Per-Service LLM Context File (service.llm.yaml)
- ADR 0349: Agent Capability Manifest and Peer Discovery
