# Network Impairment Matrix

## Purpose

Use this runbook to validate and render the ADR 0189 network impairment matrix for staging, preview, fixture, standby, and recovery targets without directly impairing the live production path.

## Repo Surfaces

- `config/network-impairment-matrix.yaml`
- `config/service-capability-catalog.json`
- `config/fault-scenarios.yaml`
- `scripts/network_impairment_matrix.py`
- `config/windmill/scripts/network-impairment-matrix.py`
- `platform/faults/network_impairment_matrix.py`

## Validate The Matrix

```bash
python3 -m py_compile scripts/network_impairment_matrix.py config/windmill/scripts/network-impairment-matrix.py platform/faults/network_impairment_matrix.py
uv run --with pytest --with pyyaml python -m pytest tests/test_network_impairment_matrix.py tests/test_network_impairment_matrix_repo_surfaces.py tests/test_network_impairment_matrix_windmill.py -q
uv run --with pyyaml python scripts/network_impairment_matrix.py --repo-path /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server --validate
uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate
```

Expected:

- the matrix validates cleanly against the service catalog and the current fault-scenario catalog
- the report writer creates `.local/network-impairment-matrix/latest.json`
- `make validate` and the focused matrix tests stay green after any matrix edit

## Render The Current Plan

Render the full matrix:

```bash
uv run --with pyyaml python scripts/network_impairment_matrix.py --repo-path /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server --format text
```

Render the default live staging slice:

```bash
uv run --with pyyaml python scripts/network_impairment_matrix.py --repo-path /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server --target-class staging
```

Render through the governed Windmill path:

```bash
make network-impairment-matrix NETWORK_IMPAIRMENT_MATRIX_ARGS='target_class=staging'
```

Expected:

- the staging slice returns the `api_gateway`, `openbao`, and `windmill` dependency rows
- each row shows the declared behaviour, target classes, impairment list, and service-catalog `fault:*` reference

## Windmill Verification

From a controller with the mirrored Windmill superadmin secret:

```bash
python3 config/windmill/scripts/network-impairment-matrix.py --repo-path /srv/proxmox_florin_server --target-class staging
curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/scripts/get/p/f%2Flv3%2Fnetwork-impairment-matrix | jq '{path, summary}'
```

Expected:

- the wrapper returns `status: planned`
- the `f/lv3/network-impairment-matrix` script path exists on the live worker

## Live Apply Checklist

1. Run the focused matrix tests and `make syntax-check-windmill`.
2. Run `uv run --with pyyaml python scripts/workflow_catalog.py --validate`.
3. Replay the Windmill runtime from the released checkout with `make live-apply-service service=windmill env=production EXTRA_ARGS='-e bypass_promotion=true'`.
4. Verify `f/lv3/network-impairment-matrix` exists through the Windmill API.
5. Trigger `make network-impairment-matrix NETWORK_IMPAIRMENT_MATRIX_ARGS='target_class=staging'`.
6. Record the generated report path plus the live verification evidence in a receipt under `receipts/live-applies/`.

## Notes

- ADR 0189 defines the safe matrix and assertion contract. It does not authorize ad hoc production network chaos.
- The current live rollout seeds a safe diagnostic workflow only; actual preview and fixture execution lanes remain follow-up work under ADR 0185 and ADR 0088.
- If the Windmill API returns editable-build or missing-`PyYAML` bootstrap errors for repo-managed scripts, replay `make live-apply-service service=windmill env=production EXTRA_ARGS='-e bypass_promotion=true'` so the worker checkout is resynchronized and stale packaging metadata is pruned before retrying the governed job.
