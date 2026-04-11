# Workstream ADR 0172: Watchdog Escalation and Stale Job Self-Healing

- ADR: [ADR 0172](../adr/0172-watchdog-escalation-and-stale-job-self-healing.md)
- Title: Extend the scheduler watchdog with stale-job detection, repeated-action escalation, heartbeat emission, and a repo-managed ten-second Windmill schedule
- Status: merged
- Branch: `codex/adr-0172-watchdog`
- Worktree: `.worktrees/codex-adr-0172-watchdog`
- Owner: codex
- Depends On: `adr-0044-windmill`, `adr-0115-mutation-ledger`, `adr-0119-budgeted-workflow-scheduler`
- Conflicts With: none
- Shared Surfaces: `platform/scheduler/watchdog.py`, `platform/scheduler/scheduler.py`, `windmill/scheduler/watchdog-loop.py`, `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`, `config/workflow-catalog.json`, `config/ledger-event-types.yaml`, `docs/runbooks/budgeted-workflow-scheduler.md`

## Scope

- extend `platform/scheduler/watchdog.py` with stale-job detection based on last observed activity
- discover running mutation jobs directly from the Windmill jobs API when local scheduler state is absent
- persist watchdog action history and escalate repeated self-healing actions after three events in ten minutes
- emit a watchdog heartbeat file plus `platform.watchdog.heartbeat` events on every tick
- seed and enable a repo-managed `f/lv3/scheduler_watchdog_loop` Windmill script on a ten-second schedule
- document the operational verification path for the watchdog loop

## Non-Goals

- adding a separate canonical lock-registry, intent-queue, or abandoned-session cleanup surface on this branch
- introducing a dedicated service-topology entry for the watchdog before the control-plane topology is ready to host it
- changing the scheduler scope beyond `execution_class: mutation`

## Expected Repo Surfaces

- `platform/scheduler/watchdog.py`
- `platform/scheduler/scheduler.py`
- `windmill/scheduler/watchdog-loop.py`
- `collections/ansible_collections/lv3/platform/roles/windmill_runtime/defaults/main.yml`
- `config/workflow-catalog.json`
- `config/ledger-event-types.yaml`
- `docs/adr/0172-watchdog-escalation-and-stale-job-self-healing.md`
- `docs/workstreams/adr-0172-watchdog-escalation-and-stale-job-self-healing.md`
- `docs/runbooks/budgeted-workflow-scheduler.md`

## Expected Live Surfaces

- Windmill seeds `f/lv3/scheduler_watchdog_loop`
- Windmill enables `f/lv3/scheduler_watchdog_loop_every_10s`
- `.local/scheduler/watchdog-heartbeat.json` updates on the runtime worker after each tick
- stale mutation jobs emit `execution.stale_job_detected` before cancellation

## Verification

- Run `python3 -m py_compile platform/scheduler/*.py windmill/scheduler/watchdog-loop.py`
- Run `uv run --with pytest python -m pytest tests/unit/test_scheduler_budgets.py tests/test_health_repo_surfaces.py -q`
- Run `python3 windmill/scheduler/watchdog-loop.py --repo-path .`

## Merge Criteria

- stale-job detection is covered by unit tests
- direct Windmill job discovery is covered by unit tests
- the seeded Windmill defaults contain the watchdog script and ten-second schedule
- the heartbeat file is written on each watchdog tick

## Outcome

- repository implementation completed in `0.146.2`
- the watchdog now aborts stale mutation jobs, records repeated-action history, and emits a heartbeat file per tick
- the Windmill runtime defaults now seed and enable a ten-second watchdog schedule
- the live apply is still pending because the limited `playbooks/windmill.yml --limit docker-runtime` rollout reached the pre-existing OpenBao secret-injection step, then failed while waiting for the local OpenBao API and later hit SSH banner-exchange timeouts through the public Proxmox host jump

## Notes For The Next Assistant

- The public Proxmox host at `203.0.113.1` now accepts the repo key as `root`, and a direct SSH proxy through that host to `ops@10.10.10.20` worked before the later banner-exchange failures began.
- A limited live apply using `playbooks/windmill.yml --limit docker-runtime` with `proxmox_guest_ssh_connection_mode=proxmox_host_jump`, `proxmox_host_admin_user=root`, and a public-host inventory override reached `lv3.platform.windmill_runtime`.
- That rollout synchronized the worker checkout and rewrote the watchdog-capable repo content on `docker-runtime`, but it did not reach the later Windmill API script or schedule seeding tasks.
- The blocking task is `Wait for the local OpenBao API` inside `lv3.platform.common` `openbao_compose_env`, followed by intermittent `Connection timed out during banner exchange` failures on the SSH proxy path.
- After the first successful `playbooks/windmill.yml` converge from `main`, verify the schedule exists in Windmill and that `.local/scheduler/watchdog-heartbeat.json` advances on `docker-runtime`.
- Do not mark this workstream `live_applied` or bump `platform_version` until that verification is complete.
