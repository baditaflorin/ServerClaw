# Agent Coordination Map

## Purpose

Operate and verify the ADR 0161 real-time agent coordination map that tracks active agent sessions, their current phase, current target, and heartbeat status.

## Repo Surfaces

- runtime store: `platform/agent/coordination.py`
- agent publishers: `platform/closure_loop/engine.py`, `config/windmill/scripts/platform-observation-loop.py`
- gateway read surface: `scripts/api_gateway/main.py`
- interactive portal view: `scripts/ops_portal/`
- static portal snapshot rendering: `scripts/generate_ops_portal.py`
- snapshot tool: `scripts/agent_coordination_snapshot.py`

## Local Validation

Run the focused suites:

```bash
uv run --with pytest --with-requirements requirements/api-gateway.txt python -m pytest -q tests/test_agent_coordination.py tests/test_api_gateway.py
uv run --with pytest --with pyyaml --with jsonschema --with-requirements requirements/ops-portal.txt python -m pytest -q tests/test_interactive_ops_portal.py tests/test_ops_portal.py
uv run --with pytest --with pyyaml python -m pytest -q tests/unit/test_closure_loop.py tests/test_closure_loop_windmill.py
uv run --with pyyaml --with jsonschema python scripts/generate_ops_portal.py --check
python3 scripts/agent_coordination_snapshot.py --repo-root .
```

## Live Runtime Inputs

The gateway reads the coordination map from JetStream KV when these environment variables are present:

- `NATS_URL`
- `LV3_NATS_USERNAME`
- `LV3_NATS_PASSWORD`

When those values are not set, the coordination store falls back to the controller-local secret manifest if `config/controller-local-secrets.json` points at a readable `nats_jetstream_admin_password` file.

## Converge

Update the live gateway and portal stacks after merging the repo change:

```bash
ansible-playbook -i inventory/hosts.yml -e proxmox_guest_ssh_connection_mode=proxmox_host_jump playbooks/api-gateway.yml
ansible-playbook -i inventory/hosts.yml -e proxmox_guest_ssh_connection_mode=proxmox_host_jump playbooks/ops-portal.yml
```

## Verify

From `docker-runtime-lv3`:

```bash
curl -sf http://127.0.0.1:8083/healthz
curl -sf http://127.0.0.1:8092/health
```

From an operator workstation with a valid bearer token:

```bash
curl -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/platform/agents
```

Expected result:

- the payload contains `summary` and `entries`
- active sessions include an `agent_id`, `current_phase`, `current_target`, and `last_heartbeat`

From the browser:

- open `https://ops.lv3.org`
- confirm the `Agent Coordination` section renders
- verify the panel updates after a new observation-loop or closure-loop run starts

## Record A Snapshot Receipt

Write the current coordination map into the repo evidence set:

```bash
python3 scripts/agent_coordination_snapshot.py --repo-root . --write
```

That writes one JSON snapshot under `receipts/agent-coordination/` for the static portal and future incident review.

## Troubleshooting

- If `/v1/platform/agents` returns an empty list while agent jobs are running, check the gateway container environment for `NATS_URL`, `LV3_NATS_USERNAME`, and `LV3_NATS_PASSWORD`.
- If the interactive portal loads but the coordination panel shows a warning banner, inspect the gateway logs first; the portal only renders the gateway response.
- If an agent vanishes unexpectedly, compare `last_heartbeat` against the TTL window. Entries expire automatically after five minutes when the heartbeat stops.
- The coordination map is a cooperative signal layer. If a conflict still occurs, check the lock and scheduler evidence rather than assuming the map is authoritative.
