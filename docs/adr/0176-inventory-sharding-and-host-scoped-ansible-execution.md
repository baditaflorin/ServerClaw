# ADR 0176: Inventory Sharding and Host-Scoped Ansible Execution

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-26

## Context

Parallel Ansible execution is only safe when the target scope is explicit. In a mixed repository, one playbook may only need `backup-lv3`, another may only touch `monitoring-lv3`, while a third mutates shared Proxmox host state. If they all execute against broad inventory groups, safe concurrency collapses into either unnecessary serialization or risky overlap.

The platform now has clear VM-level isolation and lane concepts, but Ansible execution still needs a matching repository-side targeting model.

## Decision

We will structure mutable Ansible execution around **inventory shards** and **host-scoped play metadata**.

### Shard model

Each mutable playbook declares a shard class:

- `host`: exactly one host
- `lane`: one VM-scoped execution lane
- `platform`: cross-host or shared-platform mutation

Example metadata:

```yaml
playbook_id: monitoring-stack
mutation_scope: host
target_hosts:
  - monitoring-lv3
shared_surfaces:
  - inventory/host_vars/monitoring-lv3.yml
```

### Execution rules

- `host` scoped plays may run in parallel if they target different hosts
- `lane` scoped plays follow the lane budget and lock rules from ADR 0154 and ADR 0157
- `platform` scoped plays serialize unless they declare independent shared surfaces and pass contract checks
- mutation playbooks may not target `all` unless explicitly marked as integration-only

### Repo layout consequence

Playbooks should continue to be grouped by concern, but every mutable playbook must advertise its scope in a discoverable machine-readable way so schedulers and reviewers can understand whether parallel execution is allowed.

## Consequences

**Positive**

- Parallel plays become intentional rather than accidental.
- Broad, risky host patterns are easier to detect and reject.
- The scheduler can map Ansible work directly to the runtime lane model.

**Negative / Trade-offs**

- Existing playbooks will need metadata backfill.
- Some current "convenience" playbooks that touch many surfaces will need to be split.

## Boundaries

- This ADR is about target scope and safe parallelism, not role internals.
- Read-only audit plays may still use broad inventory targets when they do not mutate state.

## Related ADRs

- ADR 0048: Command catalog
- ADR 0154: VM-scoped parallel execution lanes
- ADR 0157: Per-VM concurrency budget and resource reservation
- ADR 0178: Dependency wave manifests for parallel apply
