# ADR 0105: Platform Capacity Model and Resource Quota Enforcement

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.115.0
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-24
- Date: 2026-03-23

## Context

The Proxmox host is a single physical machine with fixed resources: 128 GB RAM, 32 vCPU, and a finite local NVMe pool. Until this ADR, VM sizing lived mostly in operator memory and ad hoc `qm config` inspection. That left the platform without one declared answer to:

- what is physically available on the host
- what each VM is currently allocated
- what each VM is allowed to grow to before review
- how much headroom must remain for Proxmox itself and for the planned ephemeral fixture pool

The monitoring stack already collects host and guest utilisation through Telegraf into InfluxDB, but there was no repo-managed model joining those live metrics to the committed VM allocations.

## Decision

We will keep a repository-managed capacity model for the Proxmox host, use it to render operator-facing reports, and expose the same model to repository validation and the promotion gate.

## Implementation

### Capacity model

The canonical model lives in `config/capacity-model.json` and is validated by `docs/schema/capacity-model.schema.json`.

The model records:

- physical host capacity and target utilisation ceilings
- resources reserved for the platform itself
- active guest allocations validated from live `qm config` output
- planned capacity for `postgres-replica-lv3`
- reserved headroom for the ADR 0106 ephemeral fixture pool

### Live utilisation collection

`scripts/capacity_report.py` reads the committed model and, when live metrics are enabled, SSHes to `monitoring-lv3` through the Proxmox jump host. On the monitoring VM it runs `influx query` against the local InfluxDB API.

The current live metrics contract is:

- memory: 7-day mean of `mem.used`
- CPU: 7-day p95 of `cpu.usage_active` for `cpu-total`
- disk: latest `disk.used` sample for `/`

If the monitoring path is unavailable, the report still renders and marks live metrics as unavailable instead of failing closed.

### Report outputs

The same script renders:

- human-readable text for operators
- markdown for the weekly Mattermost report
- JSON for automation
- Prometheus exposition format for future dashboard and alert ingestion

The primary entry points are:

- `make capacity-report`
- `lv3 capacity`
- `python3 scripts/capacity_report.py --check-gate --proposed-change <ram_gb,vcpu,disk_gb>`

### Promotion gate integration

ADR 0073 now imports the capacity model and runs the baseline capacity gate before approving a promotion. The current promotion pipeline does not yet calculate per-service VM deltas, so the integrated gate enforces the active committed-capacity baseline from the model. The reusable explicit-delta path is already implemented in `scripts/capacity_report.py` for provisioning and future promotion callers.

### Weekly report and repo-side artefacts

The repository now includes:

- `config/windmill/scripts/weekly-capacity-report.py`
- `config/grafana/dashboards/capacity-overview.json`
- `config/alertmanager/rules/platform.yml`
- `docs/runbooks/capacity-model.md`

These are repository implementations. They do not imply that the dashboard or alert rules have been applied live yet.

## Consequences

### Positive

- host capacity, VM allocations, planned growth, and reserved ephemeral headroom now live in one canonical repo model
- weekly and on-demand reporting use the same code path
- repository validation blocks broken capacity-model updates before merge
- the promotion gate now has a first-class capacity signal instead of relying on operator intuition

### Trade-offs

- the model must still be kept in sync with live `qm config` changes
- disk live metrics currently use `/` only; the backup datastore disk remains modeled from committed capacity, not a richer datastore API integration
- promotion gating currently knows baseline capacity but not service-specific VM resize deltas

## Alternatives Considered

- Proxmox-only resource tracking: rejected because it does not produce repo-managed budgets, promotion gate inputs, or reusable report formats
- reactive resizing only: rejected because it turns capacity planning into incident response
- external capacity planning software: rejected as disproportionate for the current single-node platform

## Related ADRs

- ADR 0010: Initial Proxmox VM topology
- ADR 0073: Environment promotion gate and deployment pipeline
- ADR 0085: OpenTofu VM lifecycle
- ADR 0098: Postgres HA
- ADR 0106: Ephemeral environment lifecycle and teardown policy
