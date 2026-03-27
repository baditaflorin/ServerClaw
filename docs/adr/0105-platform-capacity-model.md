# ADR 0105: Platform Capacity Model and Resource Quota Enforcement

- Status: Implemented
- Implementation Status: Implemented
- Implemented In Repo Version: 0.115.0
- Implemented In Platform Version: 0.130.24
- Implemented On: 2026-03-27
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
- `uv run --with pyyaml python scripts/capacity_report.py --check-gate --proposed-change <ram_gb,vcpu,disk_gb>`

### Promotion gate integration

ADR 0073 now imports the capacity model and runs the baseline capacity gate before approving a promotion. The current promotion pipeline does not yet calculate per-service VM deltas, so the integrated gate enforces the active committed-capacity baseline from the model. The reusable explicit-delta path is already implemented in `scripts/capacity_report.py` for provisioning and future promotion callers.

### Weekly report and repo-side artefacts

The repository now includes:

- `config/windmill/scripts/weekly-capacity-report.py`
- `config/grafana/dashboards/capacity-overview.json`
- `config/alertmanager/rules/platform.yml`
- `docs/runbooks/capacity-model.md`

On 2026-03-26 the monitoring role was extended so the Grafana converge now imports the capacity dashboard live, and the weekly Windmill wrapper was fixed to resolve `scripts/capacity_report.py` from a fresh parallel worktree checkout. The production monitoring replay verified the dashboard uid `lv3-capacity-overview`, the repo-managed platform alert bundle, and both operator report entry points with live `ssh+influx` metrics.

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

## Verification

- `uv run --with pytest python -m pytest tests/test_monitoring_vm_role.py tests/test_capacity_report.py tests/test_lv3_cli.py tests/test_promotion_pipeline.py -q`
- `uv run --with pytest python -m pytest tests/test_weekly_capacity_report_windmill.py -q`
- `uv run --with pytest python -m pytest tests/test_run_namespace.py tests/test_ansible_execution_scopes.py tests/test_remote_exec.py -q`
- `make syntax-check-monitoring`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `./scripts/validate_repo.sh alert-rules health-probes`
- `make capacity-report NO_LIVE_METRICS=true`
- `make capacity-report`
- `make weekly-capacity-report NO_LIVE_METRICS=true`
- `make weekly-capacity-report`
- `uv run --with pyyaml python scripts/capacity_report.py --model config/capacity-model.json --check-gate --proposed-change 20,8,100`
- `BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 make live-apply-service service=grafana env=production EXTRA_ARGS='-e bypass_promotion=true'`
- `curl -Ik --resolve grafana.lv3.org:443:65.108.75.123 https://grafana.lv3.org/d/lv3-capacity-overview/lv3-capacity-overview`

The first 2026-03-26 production converge imported and verified the capacity dashboard but later hit a transient SSH reachability failure during a downstream blackbox verification task. An immediate replay from the same `codex/ws-0105-live-apply` worktree then completed cleanly with `ok=176 changed=0 unreachable=0 failed=0 skipped=34`. The current-mainline replay from source commit `2907637daca87ee2bb739c0dd821eee0834aa319` completed cleanly again on 2026-03-27 with `ok=176 changed=0 unreachable=0 failed=0 skipped=34`, and that replay also verified the fresh-worktree automation path after shortening per-run Ansible control-socket directories for long isolated worktrees. The public dashboard URL `https://grafana.lv3.org/d/lv3-capacity-overview/lv3-capacity-overview` returned `HTTP/2 302` to Grafana login, and both report entry points rendered with `metrics_source: ssh+influx`.

## Related ADRs

- ADR 0010: Initial Proxmox VM topology
- ADR 0073: Environment promotion gate and deployment pipeline
- ADR 0085: OpenTofu VM lifecycle
- ADR 0098: Postgres HA
- ADR 0106: Ephemeral environment lifecycle and teardown policy
