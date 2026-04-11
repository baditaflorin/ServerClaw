# Workstream ws-0276-live-apply: Live Apply ADR 0276 From Latest `origin/main`

- ADR: [ADR 0276](../adr/0276-nats-jetstream-as-the-platform-event-bus.md)
- Title: Recover and repo-manage the private NATS JetStream runtime, then verify the ADR 0276 event-bus contract live
- Status: live_applied
- Included In Repo Version: 0.177.97
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0276-nats-jetstream-event-bus-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0276-nats-jetstream-event-bus-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.64
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0276-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0276-live-apply`
- Owner: codex
- Depends On: `adr-0023-docker-runtime-guest`, `adr-0065-secret-rotation-automation`, `adr-0079-playbook-decomposition-and-shared-execution-model`, `adr-0115-mutation-ledger`, `adr-0124-platform-event-taxonomy`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0276`, `docs/workstreams/ws-0276-live-apply.md`, `docs/runbooks/nats-jetstream-event-bus.md`, `config/nats-streams.yaml`, `playbooks/nats-jetstream.yml`, `roles/nats_jetstream_runtime/`, `scripts/nats_streams.py`, `scripts/secret_rotation.py`, `platform/ledger/writer.py`, `workstreams.yaml`, `receipts/live-applies/`

## Scope

- bring the currently stopped `lv3-nats-jetstream` runtime under repo-managed automation
- reconcile ADR 0276 launch subjects with the existing platform event taxonomy without destroying the live `PLATFORM_EVENTS` history
- verify the current mutation-ledger and secret-rotation publishers use the ADR 0276 subjects
- perform the runtime converge and stream reconcile from this isolated worktree, then record exact evidence for merge-to-main

## Non-Goals

- implementing ADR 0274 or ADR 0275 application-level RAG ingestion consumers
- changing protected release files before the final integration step on `main`
- pretending the previous host-local `/opt/nats-jetstream` state was already repo-managed

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0276-live-apply.md`
- `docs/adr/0276-nats-jetstream-as-the-platform-event-bus.md`
- `docs/runbooks/nats-jetstream-event-bus.md`
- `config/nats-streams.yaml`
- `config/event-taxonomy.yaml`
- `config/control-plane-lanes.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/service-capability-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `playbooks/nats-jetstream.yml`
- `playbooks/services/nats-jetstream.yml`
- `roles/nats_jetstream_runtime/`
- `scripts/nats_streams.py`
- `scripts/secret_rotation.py`
- `platform/ledger/writer.py`
- `tests/test_secret_rotation.py`
- `tests/test_service_id_resolver.py`
- `tests/unit/test_event_taxonomy.py`
- `tests/unit/test_ledger_writer.py`
- `receipts/live-applies/`

## Expected Live Surfaces

- `docker-runtime` serves NATS on TCP `4222` and monitoring on loopback `8222`
- JetStream exposes the committed `PLATFORM_EVENTS`, `RAG_DOCUMENT`, and `SECRET_ROTATION` streams
- `platform.mutation.recorded` publishes into `PLATFORM_EVENTS`
- `secret.rotation.completed` publishes into `SECRET_ROTATION`

## Ownership Notes

- this workstream owns the repo-managed recovery of the currently stopped NATS runtime plus the ADR 0276 stream and subject contract
- `platform.mutation.recorded` remains inside `PLATFORM_EVENTS` by design so the live rollout does not destroy the existing `platform.>` stream history
- if the branch-local live apply completes before safe main integration, the handoff must state exactly which release and integrated-truth files still wait for the merge step

## Purpose

Implement ADR 0276 by making the private NATS JetStream runtime repo-managed,
preserving the live multi-principal auth contract already used by other
consumers, and leaving a clean branch-local audit trail that an exact-main
replay can promote onto the protected `main` surfaces safely.

## Branch-Local Delivery

- `27c676e46` added the repo-managed NATS JetStream playbooks and role,
  aligned the mutation-ledger and secret-rotation subjects with the ADR 0276
  contract, updated the NATS stream catalog, and recorded the initial
  workstream surfaces.
- `959b10f38` preserved the live additional principal catalog
  (`control-plane-publisher`, `workflow-consumer`, `alert-consumer`,
  `receipt-consumer`, and `agent-consumer`) so the repo-managed runtime matches
  the live multi-principal NATS contract instead of collapsing it back to a
  single admin account.

## Verification

- The rebased branch-local proof is recorded in
  `receipts/live-applies/2026-03-30-adr-0276-nats-jetstream-event-bus-live-apply.json`
  from commit `959b10f382ff96e7a16db56a1283e83cca9fb8ea` on top of repository
  version `0.177.96` and platform version `0.130.63`.
- The canonical exact-main replay now points at committed source
  `11009b71644263cb59832c290183696483035b37`, the release cut for
  repository version `0.177.97`.
- `uv run --with pytest -m pytest -q tests/test_nats_jetstream_runtime_role.py tests/test_secret_rotation.py tests/test_service_id_resolver.py tests/unit/test_event_taxonomy.py tests/unit/test_ledger_writer.py tests/test_ansible_execution_scopes.py`
  returned `38 passed in 0.68s` on the rebased head.
- `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0276syntax-postrebase --playbook playbooks/nats-jetstream.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check`
  passed on the rebased tree, and `make preflight WORKFLOW=live-apply-service`
  also passed.
- `ANSIBLE_HOST_KEY_CHECKING=False uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0276recover-r1 --playbook playbooks/nats-jetstream.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
  succeeded with final recap
  `docker-runtime : ok=79 changed=1 unreachable=0 failed=0 skipped=6 rescued=0 ignored=0`
  after the latest server inspection found `lv3-nats-jetstream` had exited.
- `make check-nats-streams` and `make apply-nats-streams` both returned
  `PLATFORM_EVENTS: none`, `RAG_DOCUMENT: none`, and
  `SECRET_ROTATION: none` after the recovery replay.
- The first exact-main replay `ws0276mainline-r1` succeeded from the
  `0.177.97` release tree, then a shared Docker-runtime restart path left
  `lv3-nats-jetstream` manually stopped with exit code `0` after a
  `terminated` signal. A direct guest probe confirmed the container was
  not crashing, it had simply been stopped during shared runtime churn.
- A temporary compose restart from `/opt/nats-jetstream/docker-compose.yml`
  restored service health, after which the authoritative exact-main replay
  `ws0276mainline-r2` completed successfully with final recap
  `docker-runtime : ok=80 changed=4 unreachable=0 failed=0 skipped=6 rescued=0 ignored=0`
  and re-verified the NATS loopback monitor endpoint.
- After that exact-main replay, `make check-nats-streams` and
  `make apply-nats-streams` both again returned `PLATFORM_EVENTS: none`,
  `RAG_DOCUMENT: none`, and `SECRET_ROTATION: none`.
- `uv run --with pyyaml --with nats-py python scripts/nats_streams.py --smoke-publish`
  published `platform.findings.observation` into `PLATFORM_EVENTS` at
  sequence `169`, and follow-up raw JSON publishes to
  `secret.rotation.completed` and `rag.document.staged` landed in
  `SECRET_ROTATION` and `RAG_DOCUMENT` with stream-local sequence `2`.
- The canonical exact-main publish smokes then advanced
  `PLATFORM_EVENTS` to sequence `170`, and advanced both
  `SECRET_ROTATION` and `RAG_DOCUMENT` to stream-local sequence `3`.

## Outcome

- ADR 0276 is now implemented on integrated repository version `0.177.97`.
- The platform version now advances from `0.130.63` to `0.130.64` because the
  exact-main replay re-verified the private NATS JetStream event bus from the
  committed release tree.
- `receipts/live-applies/2026-03-30-adr-0276-nats-jetstream-event-bus-mainline-live-apply.json`
  supersedes the branch-local receipt as the canonical proof while preserving
  the earlier branch-local receipt and the short correction loop in the audit
  trail.
