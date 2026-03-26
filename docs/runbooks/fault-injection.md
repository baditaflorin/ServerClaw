# Fault Injection

Use this runbook to execute the ADR 0171 controlled fault-injection suite against the live `docker-runtime-lv3` control-plane services.

## Scope

- scenario catalog: [config/fault-scenarios.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/fault-scenarios.yaml)
- worker wrapper: [config/windmill/scripts/fault-injection.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/windmill/scripts/fault-injection.py)
- runner: [scripts/fault_injection.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/fault_injection.py)
- framework: [platform/faults/injector.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/faults/injector.py)

The first implementation intentionally targets the local `docker-runtime-lv3` subset only:

- `fault:keycloak-unavailable`
- `fault:openbao-unavailable`

The initial subset keeps the drills bounded and reversible: Keycloak uses a stop/start outage, while OpenBao uses pause/unpause so the singleton secret store does not come back sealed after the check.

## Manual Execution

Trigger one scenario through the governed Windmill path:

```bash
make fault-injection FAULT_INJECTION_ARGS='scenario_names=fault:keycloak-unavailable'
```

Trigger the current monthly subset:

```bash
make fault-injection FAULT_INJECTION_ARGS='scenario_names=fault:keycloak-unavailable,fault:openbao-unavailable'
```

If you need to inspect the worker-side plan without applying a fault:

```bash
uv run --with pyyaml python config/windmill/scripts/fault-injection.py --repo-path /srv/proxmox_florin_server --scenario-names fault:keycloak-unavailable --dry-run
```

## Expected Outputs

- latest JSON report under `.local/fault-injection/latest.json`
- local ledger-style event stream under `.local/state/ledger/fault-injection.events.jsonl`
- optional Mattermost and GlitchTip notifications when the worker environment exposes the corresponding webhook secrets or env vars

## Scheduled Run

The Windmill schedule is enabled weekly at `03:00 UTC` on Sundays, but the script applies a first-Sunday guard. On the second, third, fourth, and fifth Sundays it exits with `status=skipped`.

Current scheduled subset:

- `fault:keycloak-unavailable`
- `fault:openbao-unavailable`

## Live Apply Checklist

1. Run `python3 -m py_compile scripts/fault_injection.py config/windmill/scripts/fault-injection.py platform/faults/injector.py`.
2. Run `uv run --with pytest --with pyyaml python -m pytest tests/test_fault_injection.py tests/test_fault_injection_repo_surfaces.py tests/test_fault_injection_windmill.py tests/test_windmill_operator_admin_app.py -q`.
3. Run `make syntax-check-windmill` and `uv run --with pyyaml python scripts/workflow_catalog.py --validate`.
4. Replay the Windmill runtime from released `main` or otherwise confirm the guest checkout contains the released `config/windmill/scripts/fault-injection.py`.
5. Trigger the governed workflow from `main` with `make fault-injection ...`.
6. Record the live-apply receipt and update `versions/stack.yaml`, the ADR status block, and the workstream status in the same integration change.

## Troubleshooting

- If the Windmill API returns `404` for `f/lv3/fault-injection` after the runtime replay, confirm the guest checkout at `/srv/proxmox_florin_server` contains the released script, seed the script locally through the guest Windmill API from that checkout, and record that manual recovery step in the live-apply receipt before closing the rollout.
- If the shared `playbooks/windmill.yml` replay fails later in unrelated raw-app sync with `password authentication failed for user "windmill_admin"`, treat that as a separate Windmill admin-surface issue after verifying the fault-injection script and schedule surfaces already landed.
