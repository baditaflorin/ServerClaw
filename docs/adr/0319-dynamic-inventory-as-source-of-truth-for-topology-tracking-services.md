# ADR 0319: Dynamic Inventory as Source of Truth for Topology-Tracking Services

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.5
- Date: 2026-04-05

## Context

Some platform services deploy agents or children onto every managed VM (e.g.
Netdata children, log shippers). These services were wired with hardcoded host
lists in two places:

1. The Ansible role `defaults/main.yml` — an explicit list of inventory
   hostnames.
2. The playbook `hosts:` pattern — matching that same static list.

When a new VM was added to `inventory/hosts.yml`, neither location updated
automatically. The VM was provisioned and running, but invisible to services
like `realtime.example.com` until a human or agent noticed the gap and re-ran the
relevant playbook.

Two additional gaps followed:

- LLM agents had no machine-readable contract telling them which services needed
  re-convergence after inventory changes.
- `playbooks/groups/observability.yml` did not include the realtime service, so
  full-site runs (`site.yml`) silently skipped it.

## Decision

### 1. Inventory groups are the canonical host source

Any service that installs agents on managed VMs MUST derive its host list from
the existing inventory groups (`lv3_guests`, `proxmox_hosts`) rather than
maintaining a parallel static list in role defaults.

Pattern for role defaults:

```yaml
# Derived from lv3_guests + proxmox_hosts, minus the service's own parent host
topology_tracking_child_hosts: >-
  {{ (groups['lv3_guests'] + groups['proxmox_hosts'])
     | unique
     | intersect(groups[playbook_execution_env | default('production')])
     | difference([topology_tracking_parent_host]) }}
```

Pattern for playbook `hosts:`:

```yaml
hosts: "lv3_guests:proxmox_hosts:&{{ playbook_execution_env }}:!{{ monitoring_parent_host }}"
```

Adding a VM to `lv3_guests` is now the single authoritative act. The service
playbook automatically targets it on the next converge.

### 2. Group playbooks are the re-convergence path

Every topology-tracking service MUST be listed in the appropriate
`playbooks/groups/<concern>.yml` file so that a full `site.yml` run satisfies
all cross-service dependencies without extra steps.

`realtime.yml` is added to `playbooks/groups/observability.yml`.

### 3. AGENTS.md holds the cross-service wiring table

`AGENTS.md` carries a **Cross-Service Wiring Rules** section — a compact table
mapping inventory change triggers to required follow-up actions. This is the
agent-facing contract; LLM agents read `AGENTS.md` at session start per ADR
0163.

Current table:

| Trigger | Required follow-up | Why |
|---|---|---|
| VM added to / removed from `lv3_guests` | `make live-apply-service service=realtime` | Netdata child topology derived from `lv3_guests`; new VMs invisible on realtime.example.com until Netdata is installed |
| VM added to / removed from `lv3_guests` | `make live-apply-service service=guest-log-shipping` | Loki log-agent topology derived from `lv3_guests`; new VMs produce no log streams until the agent is deployed |

New topology-tracking services MUST add a row to this table when introduced.

### 4. Targeted VM-only runs require a manual follow-up

`proxmox-install.yml` (run via `make provision-guests`) converges only the
Proxmox host and guest VMs. It does not run service playbooks. After a targeted
VM provisioning run, apply topology-tracking services manually per the
AGENTS.md table.

Full `site.yml` runs satisfy this automatically.

## Consequences

### Positive

- New VMs appear on `realtime.example.com` after the next realtime converge with no
  further code changes.
- The AGENTS.md wiring table gives any LLM agent a single-read contract; no
  ADR archaeology required.
- The pattern is reusable: any future topology-tracking service (log shippers,
  Falco agents, etc.) follows the same three-part recipe.

### Trade-offs

- Role defaults that derive from `groups[...]` evaluate at playbook runtime;
  they cannot be read meaningfully in isolation without an inventory. Consumers
  must run the role inside a full Ansible context.
- The AGENTS.md table is a soft contract — it requires discipline to update when
  new topology-tracking services are added. The ADR does not enforce this
  automatically.

## Verification

- `python3 -m pytest tests/test_realtime_playbook.py -q` passes with the
  dynamic `lv3_guests:proxmox_hosts` host pattern.
- `cat playbooks/groups/observability.yml` shows `realtime.yml` present.
- `grep -A 10 "Cross-Service Wiring" AGENTS.md` shows the wiring table.

## Related ADRs

- ADR 0196: Netdata realtime streaming metrics (first topology-tracking service)
- ADR 0163: Agent onboarding protocol (AGENTS.md as session-start contract)
- ADR 0165: Playbook and role metadata standard
