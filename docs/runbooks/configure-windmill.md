# Configure Windmill

## Purpose

This runbook converges the Windmill workflow runtime defined by ADR 0044.

It covers:

- PostgreSQL database and role provisioning on `postgres-lv3`
- private Windmill runtime deployment on `docker-runtime-lv3`
- a host-side mesh TCP proxy on `proxmox_florin` for operator access
- repo-managed workspace bootstrap and seeded script verification
- controller-local bootstrap secrets mirrored under `.local/windmill/`

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `postgres-lv3` and `docker-runtime-lv3` are already reachable through the Proxmox jump path
3. the Proxmox host is reachable on its Headscale-managed mesh address `100.64.0.1`

## Entrypoints

- syntax check: `make syntax-check-windmill`
- preflight: `make preflight WORKFLOW=converge-windmill`
- converge: `make converge-windmill`

## Delivered Surfaces

The workflow manages these live surfaces:

- PostgreSQL database `windmill` on `postgres-lv3`
- PostgreSQL login role `windmill_admin` plus support role `windmill_user` on `postgres-lv3`
- Windmill runtime under `/opt/windmill` on `docker-runtime-lv3`
- private operator entrypoint at `http://100.64.0.1:8005`
- password-login bootstrap admin `superadmin_secret@windmill.dev` backed by the managed Windmill secret
- repo-managed workspace `lv3`
- seeded script `f/lv3/windmill_healthcheck`
- seeded script `f/lv3/scheduler_watchdog_loop`
- seeded script `f/lv3/rotate_credentials`
- seeded script `f/lv3/deploy_and_promote`
- seeded helper `f/lv3/mutation_audit_emit`
- seeded helper `f/lv3/lane_scheduler`
- seeded helper `f/lv3/scheduler_watchdog`
- seeded helper `f/lv3/ephemeral_vm_reaper`
- enabled schedule `f/lv3/ephemeral_vm_reaper_every_30m`
- seeded helper `f/lv3/operator_onboard`
- seeded helper `f/lv3/operator_offboard`
- seeded helper `f/lv3/sync_operators`
- seeded helper `f/lv3/quarterly_access_review`
- enabled schedule `f/lv3/scheduler_watchdog_loop_every_10s`
- seeded helper `f/lv3/config_merge/merge_config_changes`
- enabled schedule `f/lv3/config_merge/merge_config_changes_every_minute`
- enabled schedule `f/lv3/quarterly_access_review_every_monday_0900`
- worker-runtime ADR 0108 env passthrough for Windmill audit surface labelling and optional Tailscale, step-ca, and Mattermost hooks
- worker-runtime ADR 0108 OpenBao URL override pinned to `http://lv3-openbao:8201` over the shared `openbao_default` Docker network
- normalized writable worker-checkout paths for ADR 0108 roster and state mutations
- mirrored ADR 0108 bootstrap secrets under `/srv/proxmox_florin_server/.local/` on the Windmill worker checkout
- mirrored ADR 0230 policy bundle under `/srv/proxmox_florin_server/policy` on the Windmill worker checkout
- mirrored ADR 0230 worker-safe helpers `scripts/policy_checks.py`, `scripts/policy_toolchain.py`, `scripts/command_catalog.py`, `scripts/gate_status.py`, and `config/windmill/scripts/gate-status.py`
- PostgreSQL table `config_change_staging` in the Windmill database
- enabled schedule `f/lv3/lane_scheduler_every_2s`
- enabled schedule `f/lv3/scheduler_watchdog_every_30s`

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt`

## Verification

Run these checks after converge:

1. `make syntax-check-windmill`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'docker compose --file /opt/windmill/docker-compose.yml ps && sudo ls -l /opt/windmill/openbao /run/lv3-secrets/windmill && sudo test ! -e /opt/windmill/windmill.env'`
3. `curl -s http://100.64.0.1:8005/api/version`
4. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/users/whoami`
5. `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{"probe":"manual-run"}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fwindmill_healthcheck`
6. `curl -s -X POST http://100.64.0.1:8005/api/auth/login -H "Content-Type: application/json" -d "{\"email\":\"superadmin_secret@windmill.dev\",\"password\":\"$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)\"}"`
7. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/schedules/list | grep scheduler_watchdog_loop_every_10s`
8. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'test -s /srv/proxmox_florin_server/.local/scheduler/watchdog-heartbeat.json && sudo cat /srv/proxmox_florin_server/.local/scheduler/watchdog-heartbeat.json'`
9. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.50 "psql -d windmill -Atqc \"SELECT to_regclass('public.config_change_staging')\""`
10. `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fconfig_merge%2Fmerge_config_changes`
11. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/schedules/list | jq '.[] | select(.path=="f/lv3/lane_scheduler_every_2s" or .path=="f/lv3/scheduler_watchdog_every_30s" or .path=="f/lv3/config_merge/merge_config_changes_every_minute") | {path, enabled, schedule}'`
12. `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fephemeral_vm_reaper`
13. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/schedules/list | jq '.[] | select(.path=="f/lv3/ephemeral_vm_reaper_every_30m") | {path, enabled, schedule, script_path}'`
14. `curl -s -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" http://100.64.0.1:8005/api/w/lv3/schedules/list | jq '.[] | select(.path=="f/lv3/quarterly_access_review_every_monday_0900") | {path, enabled, schedule, timezone, args}'`
15. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'sudo docker exec windmill-windmill_worker-1 env | grep -E "^(LV3_OPENBAO_URL|LV3_OPERATOR_MANAGER_SURFACE|KEYCLOAK_BOOTSTRAP_PASSWORD|OPENBAO_INIT_JSON|TAILSCALE_TAILNET|LV3_TAILSCALE_INVITE_ENDPOINT|LV3_STEP_CA_SSH_REGISTER_COMMAND|LV3_STEP_CA_SSH_REVOKE_COMMAND|LV3_MATTERMOST_WEBHOOK)=" || true'`
16. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'sudo stat -c "%A %U:%G %n" /srv/proxmox_florin_server/config/operators.yaml /srv/proxmox_florin_server/.local/state/operator-access'`
17. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime-lv3 -m shell -a 'python3 - <<\"PY\"\nfrom pathlib import Path\nimport json\npayload = Path(\"/srv/proxmox_florin_server/.local/proxmox-api/lv3-automation-primary.json\")\nlatest = sorted(Path(\"/srv/proxmox_florin_server/.local/fixtures/reaper-runs\").glob(\"reaper-run-*.json\"))[-1]\nprint(json.dumps({\"payload_exists\": payload.exists(), \"payload_mode\": oct(payload.stat().st_mode & 0o777), \"latest_receipt\": latest.name, \"latest_receipt_body\": json.loads(latest.read_text())}, indent=2, sort_keys=True))\nPY' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
18. `curl -s -X POST -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/windmill/superadmin-secret.txt)" -H "Content-Type: application/json" -d '{"findings":[{"severity":"critical","check":"manual-self-correction-contract","service_id":"windmill"}],"source":"adr-0204-manual-verify"}' http://100.64.0.1:8005/api/w/lv3/jobs/run_wait_result/p/f%2Flv3%2Fplatform_observation_loop | jq '.result.correction_loop_id, .result.processed_runs[0].correction_loop_id'`
19. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime-lv3 -m shell -a 'cd /srv/proxmox_florin_server && python3 scripts/policy_checks.py --validate && python3 scripts/command_catalog.py --check-approval --command converge-windmill --requester-class human_operator --approver-classes human_operator --validation-passed --preflight-passed --receipt-planned && python3 config/windmill/scripts/gate-status.py --repo-path /srv/proxmox_florin_server' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
20. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime-lv3 -m shell -a 'find /srv/proxmox_florin_server/policy -type f \( -name "._*" -o -name ".DS_Store" \) -print' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`

## Notes

- Windmill stays private-only in this rollout. There is no public edge publication and no public DNS record for it.
- The current bootstrap uses a repo-managed superadmin secret mirrored locally so the repository can seed and verify the runtime without UI-only state. The same managed secret currently backs the password-login bootstrap admin for browser access. Replace that with narrower identities as ADR 0046, ADR 0047, and ADR 0056 are implemented.
- No repo-managed Windmill job in this rollout stores long-lived third-party secrets inside Windmill. Secret-bearing workflows should wait for ADR 0043 or use another approved authority.
- The seeded `f/lv3/rotate_credentials` script summarizes the canonical secret-rotation catalog and is the first Windmill surface for ADR 0065.
- The seeded `f/lv3/config_merge/merge_config_changes` worker is the ADR 0158 merge writer for `config_change_staging`.
- The ADR 0106 reaper uses the mounted worker checkout as its durable credential bridge. Keep `/srv/proxmox_florin_server/.local/proxmox-api/lv3-automation-primary.json` present and `/srv/proxmox_florin_server/.local/fixtures/reaper-runs/` writable on `docker-runtime-lv3` so `run_wait_result` executions can both talk to Proxmox and persist summary receipts.
- For guest-side ADR 0106 receipt verification, prefer the inventory-driven Ansible ad-hoc command above when a direct `ssh -J ops@100.64.0.1 ...` path is not available from the current workstation.
- ADR 0108 now depends on the Windmill runtime mirroring any exported controller-side operator-manager environment values into the worker container environment. Export those variables on the controller before `make converge-windmill` when the browser-first workflow path should perform live Tailscale, step-ca, or Mattermost actions.
- Repo-managed Windmill raw apps that ship a frontend `package.json` must also ship a committed `package-lock.json`. `make converge-windmill` now resolves those frontend dependencies inside the sync container with `npm ci` before `wmill sync push`, so missing lockfiles fail the apply instead of depending on a controller-local `node_modules/`.
- ADR 0108 uses `LV3_OPENBAO_URL=http://lv3-openbao:8201` inside the Windmill worker container environment and attaches the worker containers to the external `openbao_default` Docker network. The shared OpenBao service catalog still points at the private mTLS edge on `:8200`, but the Windmill-side automation path needs direct access to the OpenBao container's HTTP automation listener instead.
- ADR 0108 also depends on the staged worker checkout keeping `config/operators.yaml` writable and `.local/state/operator-access/` writable after each sync, because Windmill jobs update the live roster and branch-local state from inside the worker checkout rather than from a controller-side clone.
- ADR 0108 mirrors the Keycloak bootstrap admin password and OpenBao init payload into the worker checkout `.local/` tree as managed runtime files because `operator_manager.py` still honors those repo-local defaults when the Windmill job sandbox does not expose the container env directly to subprocesses.
- ADR 0230 expects the worker mirror to keep the `policy/` tree and the worker-safe policy helpers in sync with the controller checkout because approval and gate-status wrappers now evaluate the shared OPA bundle locally on `docker-runtime-lv3`.
- ADR 0230 also strips `._*` and `.DS_Store` metadata from the worker checkout during sync so macOS worktrees do not poison OPA or Conftest evaluation on the Linux runtime.
- ADR 0172 owns the live scheduler watchdog seed and schedule. ADR 0170 aligns the timeout hierarchy used around that path.
- ADR 0204 now expects the seeded `f/lv3/platform_observation_loop` script to report the governed correction-loop id in its JSON result and persist the same contract snapshot in the worker checkout closure-loop state.
- Backup coverage comes from the existing VM backup policy: `postgres-lv3` protects the Windmill database and `docker-runtime-lv3` protects the runtime filesystem and logs.
