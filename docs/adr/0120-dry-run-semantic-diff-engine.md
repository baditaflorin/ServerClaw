# ADR 0120: Dry-Run Semantic Diff Engine

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Platform changes are approved based on a description of intent ("deploy netbox to the latest version") rather than a precise description of effect ("this will change 3 container labels, restart 1 container, and update 2 DNS records"). The gap between intent and effect is where surprises happen.

Several platform components already have dry-run capabilities in isolation:

- Ansible playbooks support `--check` mode and produce a changed-task list.
- OpenTofu supports `terraform plan` and produces a resource diff.
- Caddy and nginx config changes can be syntax-validated before reload.

But these are disconnected. The operator who wants to know "what will this deployment actually change?" must run at least three separate commands, mentally merge their outputs, and then decide whether to proceed. The agent observation loop (ADR 0071) and the risk scorer (ADR 0116) need this information automatically — they cannot run three ad hoc commands before every intent compilation.

The dry-run diff engine solves this by providing a unified, object-model diff for any execution intent, across all platform surfaces, in a single API call.

## Decision

We will implement a **dry-run semantic diff engine** as a Python module `platform/diff_engine/` that computes a `SemanticDiff` — a structured description of predicted changes — for any `ExecutionIntent` before execution.

### Diff model

```python
@dataclass
class ChangedObject:
    surface: str            # 'ansible_task' | 'docker_container' | 'dns_record' | 'tls_cert' | ...
    object_id: str          # fully qualified identifier of the object being changed
    change_kind: str        # 'create' | 'update' | 'delete' | 'restart' | 'renew'
    before: dict | None     # current state (from world-state materializer)
    after: dict | None      # predicted state after change
    confidence: str         # 'exact' | 'estimated' | 'unknown'
    reversible: bool        # can this change be trivially reverted?
    notes: str | None       # human-readable explanation of the change

@dataclass
class SemanticDiff:
    intent_id: str
    computed_at: str        # ISO8601
    changed_objects: list[ChangedObject]
    total_changes: int
    irreversible_count: int
    unknown_count: int      # objects we could not assess
    adapters_used: list[str]
    elapsed_ms: int
```

### Adapters

Each platform surface has a diff adapter. Adapters are registered in `config/diff-adapters.yaml` and invoked by the engine based on the `allowed_tools` in the compiled intent:

```
platform/diff_engine/adapters/
├── ansible_adapter.py      # runs ansible-playbook --check; parses task output
├── opentofu_adapter.py     # runs tofu plan -json; parses resource changes
├── docker_adapter.py       # compares desired compose state against current Docker API state
├── dns_adapter.py          # compares desired DNS records against current NetBox/resolver state
├── cert_adapter.py         # compares desired cert config against current step-ca inventory
├── firewall_adapter.py     # compares desired nftables rules against live ruleset
└── vm_adapter.py           # compares desired Proxmox VM config against Proxmox API state
```

Each adapter implements:

```python
class DiffAdapter(Protocol):
    surface: str

    def compute_diff(
        self,
        intent: ExecutionIntent,
        world_state: WorldStateClient,
    ) -> list[ChangedObject]:
        ...
```

### Ansible adapter (primary surface)

The Ansible adapter is the most important because most platform mutations run through Ansible playbooks:

```python
class AnsibleAdapter:
    surface = "ansible_task"

    def compute_diff(self, intent, world_state):
        # Run ansible-playbook --check --diff against the target
        result = subprocess.run(
            ["ansible-playbook", "--check", "--diff",
             "-i", inventory_for(intent.target),
             playbook_for(intent.action),
             "--extra-vars", json.dumps(intent.scope.as_vars())],
            capture_output=True, text=True, timeout=60
        )

        # Parse the JSON callback output
        tasks = parse_ansible_check_output(result.stdout)

        return [
            ChangedObject(
                surface="ansible_task",
                object_id=f"{task.host}:{task.name}",
                change_kind="update",
                before=task.before,
                after=task.after,
                confidence="exact" if task.diff else "estimated",
                reversible=True,
            )
            for task in tasks if task.changed
        ]
```

### Integration with the goal compiler

The goal compiler (ADR 0112) calls the diff engine immediately after compilation, before presenting the intent to the operator. The compiled intent display includes the semantic diff:

```
$ lv3 run "deploy netbox"

Compiled intent: deploy service:netbox
Risk class: MEDIUM (score: 42/100)

Predicted changes (3 objects):
  ✎ docker_container:netbox         update   restart container with new image tag
  ✎ ansible_task:netbox:config_file update   /opt/netbox/config/configuration.py (2 lines changed)
  ✎ dns_record:netbox.lv3.org       update   TTL 300→60 (temporary low TTL for deployment)

Irreversible: 0   Unknown: 0   Adapters used: docker, ansible, dns

Proceed? [y/N]
```

### Integration with the risk scorer

The diff engine result is passed to the risk scorer (ADR 0116) as the `expected_change_count` and `irreversible_count` signals. The risk score accounts for the actual predicted surface of the change, not a generic estimate.

### Partial adapter coverage

Not all surfaces have complete adapters at launch. When an intent involves a surface with no adapter, the engine returns a `ChangedObject` with `confidence: unknown` and `change_kind: unknown`. These count toward the `unknown_count` in the diff summary and are flagged in the approval prompt.

The risk scorer treats `unknown_count > 0` as a penalty: changes with unknown surfaces have their `mutation_surface` score contribution set to the maximum rather than zero.

## Consequences

**Positive**

- Operators see the actual predicted diff, not an abstract description of intent. Change approvals are based on evidence, not trust.
- The risk scorer has a precise `expected_change_count` derived from the real diff rather than a static estimate.
- Irreversible change detection catches destructive operations (data deletion, permanent DNS changes) before they execute.
- The diff is stored in the ledger (ADR 0115) as the `before_state` baseline, so post-execution verification can compare actual vs predicted.

**Negative / Trade-offs**

- Running `ansible-playbook --check` is the most expensive part of the diff engine. For large playbooks it can take 30–60 seconds. This adds latency to every interactive `lv3 run` invocation.
- Adapter coverage is never complete. Novel infrastructure additions require new adapters before their changes are visible in the diff.
- `--check` mode in Ansible has known limitations: conditional tasks that depend on gathered facts may produce incorrect or absent diff output. These surface as `confidence: estimated` in the output.

## Boundaries

- The diff engine computes predicted changes. It does not execute any mutations.
- Diff computation is read-only with one exception: the Ansible adapter runs `ansible-playbook --check`, which may create temporary artefacts on the target host. These are explicitly safe per Ansible's check mode guarantee.
- The diff engine does not make approval decisions; it provides evidence to the goal compiler and risk scorer.

## Related ADRs

- ADR 0048: Command catalog (playbook and tool mappings used by adapters)
- ADR 0085: OpenTofu VM lifecycle (OpenTofu adapter source)
- ADR 0090: Platform CLI (diff output displayed in the `lv3 run` interactive flow)
- ADR 0112: Deterministic goal compiler (calls diff engine; includes diff in compiled intent display)
- ADR 0113: World-state materializer (before-state data source for all adapters)
- ADR 0115: Event-sourced mutation ledger (predicted diff stored as before_state baseline)
- ADR 0116: Change risk scoring (consumes expected_change_count and irreversible_count)
- ADR 0119: Budgeted workflow scheduler (uses max_touched_hosts from diff output)
