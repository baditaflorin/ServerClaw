# Windmill Default Operations Surface

## Purpose

ADR 0228 makes Windmill the default browser-first and API-first surface for repeatable repo-managed operations that already ship a Windmill wrapper.

The practical rule is simple:

- if a governed workflow declares a wrapper under `config/windmill/scripts/` and is referenced from `config/workflow-catalog.json`, it should be seeded into the `lv3` Windmill workspace by default
- if a workflow is not safe or ready to expose that way yet, fix or narrow the wrapper instead of leaving the operational path terminal-only by accident

## Canonical Surfaces

- `config/workflow-catalog.json`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/tasks/verify.yml`
- `docs/runbooks/configure-windmill.md`
- `receipts/live-applies/`

## Representative Seeded Operations

These scripts are part of the default operations surface after ADR 0228:

- `f/lv3/post_merge_gate`
- `f/lv3/nightly_integration_tests`
- `f/lv3/runbook_executor`
- `f/lv3/continuous_drift_detection`
- `f/lv3/subdomain_exposure_audit`
- `f/lv3/weekly_capacity_report`
- `f/lv3/weekly_security_scan`
- `f/lv3/security_posture_scan`
- `f/lv3/audit_token_inventory`
- `f/lv3/token_exposure_response`
- `f/lv3/maintenance_window`
- `f/lv3/collection_publish`
- `f/lv3/packer_template_rebuild`
- `f/lv3/fixture_expiry_reaper`

The existing purpose-built browser app from ADR 0122 remains part of the same Windmill-private operations boundary:

- raw app: `f/lv3/operator_access_admin`

## Discovery And API Routes

Look up script metadata:

```bash
curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" \
  http://100.64.0.1:8005/api/w/lv3/scripts/get/p/f%2Flv3%2Fweekly_capacity_report
```

Run a script and wait for the result:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" \
  -H "Content-Type: application/json" \
  -d '{"no_live_metrics":true}' \
  http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fweekly_capacity_report
```

Open the authenticated raw app route:

```text
http://100.64.0.1:8005/apps/get/p/f/lv3/operator_access_admin
```

## Verification

Focused repo validation:

```bash
uv run --with pytest --with pyyaml pytest \
  tests/test_nightly_integration_tests.py \
  tests/test_weekly_capacity_report_windmill.py \
  tests/test_ansible_collection_packaging.py \
  tests/test_windmill_default_operations_surface.py -q
python3 -m py_compile \
  config/windmill/scripts/nightly-integration-tests.py \
  config/windmill/scripts/weekly-capacity-report.py \
  config/windmill/scripts/collection-publish.py
make syntax-check-windmill
```

Representative live checks:

```bash
curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" \
  http://100.64.0.1:8005/api/w/lv3/scripts/get/p/f%2Flv3%2Fpost_merge_gate | jq '{path, summary}'

curl -s -X POST \
  -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" \
  -H "Content-Type: application/json" \
  -d '{"no_live_metrics":true}' \
  http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fweekly_capacity_report

curl -s -X POST \
  -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" \
  -H "Content-Type: application/json" \
  -d '{"dry_run":true}' \
  http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Faudit_token_inventory
```

## Notes

- Scheduled enablement remains owned by each workflow’s safety contract; ADR 0228 makes the Windmill execution surface present by default, not every schedule automatically enabled.
- Some wrappers are intentionally powerful. The repo-managed wrapper, workflow budget, runbook, and secret contracts remain the governing safety boundary; seeding the script does not bypass those controls.
- `f/lv3/maintenance_window` is part of the default surface, but the current live NATS publish authorization gap in `docs/runbooks/maintenance-windows.md` still applies.
