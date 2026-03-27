# Platform Timeout Hierarchy

## Purpose

Use this runbook when validating or reapplying ADR 0170 timeout controls across the API gateway, Windmill scheduler watchdog, SSH helper paths, and NetBox synchronization.

## Canonical Inputs

- hierarchy: [`config/timeout-hierarchy.yaml`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/timeout-hierarchy.yaml)
- runtime helpers: [`platform/timeouts/`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/platform/timeouts)
- validator: [`scripts/validate_timeout_hierarchy.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/validate_timeout_hierarchy.py)
- scanner: [`scripts/check_hardcoded_timeouts.py`](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/check_hardcoded_timeouts.py)

## Validate

```bash
uv run --with pyyaml python scripts/validate_timeout_hierarchy.py
python3 scripts/check_hardcoded_timeouts.py
uv run --with pytest --with pyyaml --with httpx==0.28.1 --with fastapi==0.116.1 --with cryptography==45.0.6 pytest tests/test_timeout_hierarchy.py tests/test_api_gateway.py tests/test_world_state_workers.py tests/unit/test_scheduler_budgets.py -q
```

## Live Apply

Apply the two runtime surfaces affected by ADR 0170:

```bash
ansible-playbook -i inventory/hosts.yml -e proxmox_guest_ssh_connection_mode=proxmox_host_jump playbooks/api-gateway.yml
ansible-playbook -i inventory/hosts.yml -e proxmox_guest_ssh_connection_mode=proxmox_host_jump playbooks/windmill.yml
```

## Verify

From the controller:

```bash
curl -sf https://api.lv3.org/healthz
ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'test -f /opt/api-gateway/config/timeout-hierarchy.yaml && grep -n LV3_TIMEOUT_HIERARCHY_PATH /opt/api-gateway/api-gateway.env'
ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'python3 /srv/proxmox_florin_server/windmill/scheduler/watchdog-loop.py --repo-path /srv/proxmox_florin_server'
```

From Windmill:

- confirm the seeded script `f/lv3/scheduler_watchdog_loop` exists
- confirm the schedule `f/lv3/scheduler_watchdog_loop_every_10s` exists and is enabled

## Expected State

- API gateway service timeouts are uniformly `30` seconds in `config/api-gateway-catalog.json`.
- API gateway runtime bundle contains `/config/timeout-hierarchy.yaml`.
- Windmill worker checkout on `docker-runtime-lv3` includes the `windmill/` tree from ADR 0172.
- The scheduler watchdog loop runs every 10 seconds with `no_flow_overlap=true`.
