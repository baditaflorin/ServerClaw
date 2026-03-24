# Dry-Run Semantic Diff Engine

ADR 0120 adds a repo-managed semantic diff stage to the `lv3 run <workflow>` path.

## Operator Use

- Run `lv3 run <workflow> --dry-run` to inspect predicted changes before any Windmill API call is made.
- Review the `Predicted changes (...)` block first, then the compiled intent YAML.
- Treat any `?` line or non-zero `Unknown:` count as operator-review-required even if the workflow is otherwise low risk.

## Adapter Coverage

- `ansible`: runs `ansible-playbook --check --diff` for workflow playbooks and maps changed tasks into `ansible_task` objects.
- `opentofu`: reads the generated `tofu plan` JSON and maps resource actions into `tofu_resource` objects.
- `docker`: compares repo-pinned image catalog entries with the `container_inventory` world-state surface.
- `dns`: compares the subdomain catalog with the `dns_records` world-state surface.
- `cert`: compares the certificate catalog with the `tls_cert_expiry` world-state surface.

## Tuning

- Enable or disable adapters in `config/diff-adapters.yaml`.
- Increase per-adapter subprocess timeouts in `config/diff-adapters.yaml` when `ansible` or `opentofu` dry runs need more headroom.
- Keep unsupported surfaces explicit. Do not hide them behind default counts if the diff engine can instead emit `confidence: unknown`.

## Verification

- `uv run --with pytest --with pyyaml pytest tests/unit/test_diff_engine.py tests/test_risk_scorer.py tests/test_lv3_cli.py tests/test_world_state_client.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `lv3 run converge-netbox --dry-run`

## Failure Modes

- If the diff block is missing entirely, check `config/diff-adapters.yaml` and the workflow metadata in `config/workflow-catalog.json`.
- If all objects are `unknown`, confirm the required world-state surfaces are present and not stale, then confirm the relevant adapter is enabled.
- If the Ansible adapter fails immediately, verify `ansible-playbook` is installed and that `inventory/hosts.yml` is reachable from the repo root.
