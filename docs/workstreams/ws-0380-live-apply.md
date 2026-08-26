# Workstream ws-0380-live-apply: ADR 0380 Neko Remote Desktop

- ADR: [ADR 0380](../adr/0380-neko-for-operator-remote-browser-access.md)
- Title: Neko remote desktop exact-main live apply and regression hardening
- Status: merged
- Branch: `codex/ws-0380-main-integration`
- Worktree: `.worktrees/ws-0380-main-integration`
- Owner: codex
- Depends On: `ADR 0153`, `ADR 0170`, `ADR 0293`, `ADR 0347`, `ADR 0380`
- Conflicts With: none

## Scope

- replay ADR 0380 from a fresh `origin/main` worktree instead of inheriting local generated state
- harden the automation path so `make converge-neko` can run from a clean checkout and reapply every owned live surface that Neko depends on
- remove stale or unsafe Neko ingress assumptions before the live apply replays them to the platform
- record branch-local verification, ADR metadata updates, and the exact mainline follow-up still required after the branch is live

## Expected Repo Surfaces

- `workstreams.yaml`
- `workstreams/active/ws-0380-live-apply.yaml`
- `docs/workstreams/ws-0380-live-apply.md`
- `docs/runbooks/configure-neko-browser-access.md`
- `docs/adr/0380-neko-for-operator-remote-browser-access.md`
- `docs/adr/.index.yaml`
- `docs/adr/index/by-concern/*.yaml`
- `docs/adr/index/by-range/*.yaml`
- `docs/adr/index/by-status/*.yaml`
- `docs/adr/implementation-status/adr-0380.yaml`
- `playbooks/neko.yml`
- `playbooks/_includes/dns_publication.yml`
- `playbooks/provision-subdomain.yml`
- `Makefile`
- `build/platform-manifest.json`
- `collections/ansible_collections/lv3/platform/playbooks/_includes/dns_publication.yml`
- `collections/ansible_collections/lv3/platform/playbooks/neko.yml`
- `collections/ansible_collections/lv3/platform/playbooks/provision-subdomain.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/derive_service_defaults.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/neko_runtime/tasks/verify.yml`
- `config/health-probe-catalog.json`
- `config/workflow-catalog.json`
- `config/worktree-bootstrap-manifests.json`
- `inventory/host_vars/proxmox-host.yml`
- `platform/ansible/execution_scopes.py`
- `publication/templates/proxmox-host.yml`
- `receipts/live-applies/*`
- `receipts/live-applies/evidence/*`
- `scripts/generate_diagrams.py`
- `scripts/generate_ops_portal.py`
- `scripts/generate_status_docs.py`
- `scripts/generate_topology_snapshot.py`
- `scripts/materialize_shared_edge_portals.py`
- `scripts/materialize_worktree_receipts.py`
- `scripts/neko_tool.py`
- `scripts/platform_manifest.py`
- `scripts/preflight_controller_local.py`
- `scripts/validate_repo.sh`
- `scripts/verify_neko_webrtc_session.py`
- `tests/test_ansible_execution_scopes.py`
- `tests/test_derive_service_defaults.py`
- `tests/test_dns_publication_include.py`
- `tests/test_docker_runtime_role.py`
- `tests/test_neko_firewall_concurrency.py`
- `tests/test_neko_ingress_contract.py`
- `tests/test_neko_timeout_hierarchy.py`
- `tests/test_neko_verification_contract.py`
- `tests/test_provision_subdomain_playbook.py`
- `tests/test_uptime_contract.py`

## Expected Live Surfaces

- Proxmox host `proxmox-host`
- VM `runtime-comms`
- VM `nginx`
- Keycloak operator group membership used to derive `neko_instances`
- public route `https://browser.example.com`
- direct UDP WebRTC media forwarding on the Proxmox host for the published Neko port range

## Initial Baseline

- `origin/main` baseline at workstream start: `86390fcc8a07fca2a58670f60ec4cf6b9d0278eb`
- fresh worktrees do not carry `inventory/group_vars/platform.yml`, so the current `converge-neko` path cannot rely on branch-local generated state already existing
- `inventory/host_vars/proxmox-host.yml` still contains stale Neko forwarding drift from the abandoned `10.10.10.41` plan and advertises an unnecessary public TCP `8080` forward for signalling
- `playbooks/neko.yml` does not currently replay `lv3.platform.proxmox_network`, even though ADR 0380 and the workflow catalog claim the live apply reprograms the Proxmox host forwarding contract
- the repo contains a legacy single-container Neko verification path and outdated example addresses that need to be brought back in line with the multi-instance runtime on `runtime-comms`

## Merge Criteria

- `make converge-neko` succeeds from this clean worktree without hidden local prerequisites
- the live apply replays the Proxmox host forwarding, the `runtime-comms` guest runtime, and the NGINX edge route from latest `origin/main`
- the public Neko route verifies end to end and the stale public TCP signalling exposure is removed
- regression coverage exists for the ingress contract and the workflow bootstrap gap
- ADR metadata, runbook guidance, and workstream state tell the next agent exactly what is live now and what still waits for mainline release integration

## Progress Notes

### 2026-04-11: Exact-Main Baseline Discovery

- created a dedicated `codex/ws-0380-live-apply` worktree from `origin/main@86390fcc8`
- confirmed the active workstream manifest was missing and created this tracked handoff surface
- identified four exact-main regressions before the first live replay:
  - the Proxmox host vars still targeted stale Neko forwarding at `10.10.10.41`
  - the Proxmox host still advertised a public TCP `8080` forward even though ADR 0380 keeps signalling behind the NGINX edge
  - `playbooks/neko.yml` claimed to replay the host forwarding contract but never ran `lv3.platform.proxmox_network`
  - `make converge-neko` depended on an untracked `inventory/group_vars/platform.yml` file that is absent in a fresh worktree

### 2026-04-12: Exact-Main Bootstrap Hardening

- added worktree bootstrap helpers for generated `platform.yml`, shared edge portal artifacts, and local receipt skeletons so `make syntax-check-neko` and `make converge-neko` work from a clean worktree instead of relying on hidden generated state
- updated `Makefile` plus `scripts/validate_repo.sh` so the Neko workflow self-installs required Ansible collections into `build/collection-install` before syntax or converge runs
- fixed the Neko controller-side verifier path to resolve the shared `.local/` overlay, tunnel through the Proxmox jump path, and follow the current Neko websocket protocol (`system/init`, `signal/provide`, `signal/answer`, query-param auth)
- repaired the shared defaults path used by scoped Neko runs so explicit `neko_instances` survive `derive_service_defaults`, `docker_runtime` no longer depends on `hostvars` or templated `proxmox_guests` during argument validation, and the browser-edge probe runs from the controller instead of from `nginx`

### 2026-04-12: Verified Live Apply

- clean-cache replay succeeded with `rm -rf build/collection-install build/collection-install.requirements.sha && make converge-neko env=production`
- replay covered the intended live surfaces end to end: Hetzner DNS publication for `browser.example.com`, Proxmox host forwarding policy, multi-instance Neko on `runtime-comms`, and shared edge publication on `nginx`
- controller-side verification passed with `python3 scripts/neko_tool.py validate` (`All 9 instance(s) are valid.`) and `uv run --with websockets --with pyyaml python3 scripts/verify_neko_webrtc_session.py --public-url https://browser.example.com --timeout 30`
- the public verifier observed the expected oauth2 redirect on `https://browser.example.com/`, selected backend `10.10.10.21:8080`, completed websocket plus SDP negotiation, and reported `VERIFICATION PASSED: Neko WebRTC is operational`
- ad-hoc host checks confirmed `runtime-comms` is listening on the expected Neko signalling ports (`8080-8088`) and the Proxmox host nftables rules forward UDP `50000-60000` to `10.10.10.21` without a matching public TCP `8080` DNAT rule

### 2026-04-12: Validation Notes

- focused regression suite passed after the final merge-closeout fixes: `uv run --with-requirements requirements/docs.txt --with pytest --with pyyaml --with jsonschema python -m pytest -q tests/test_docker_runtime_role.py tests/test_neko_verification_contract.py tests/test_neko_ingress_contract.py tests/test_neko_timeout_hierarchy.py tests/test_derive_service_defaults.py tests/test_dns_publication_include.py tests/test_ansible_execution_scopes.py tests/test_provision_subdomain_playbook.py tests/test_uptime_contract.py tests/test_materialize_shared_edge_portals.py tests/test_docs_site.py tests/test_live_apply_receipts.py tests/test_workbench_information_architecture_schema.py tests/test_validation_toolkit.py` returned `81 passed`
- `uv run --with pyyaml --with jsonschema python3 scripts/live_apply_receipts.py --validate` passed after normalizing the existing ADR 0364 receipt schema and adding the ADR 0380 receipt
- `uv run --with pyyaml python3 scripts/canonical_truth.py --check` passed after archiving the merged workstream shards and refreshing `workstreams.yaml`
- broader repo validation still reports pre-existing non-ADR-0380 issues from `origin/main` truth:
  - `uv run --with pyyaml --with jsonschema python3 scripts/validate_repository_data_models.py --validate` now gets past the workbench IA schema drift but still fails on a missing image-scan receipt referenced by `config/image-catalog.json`
  - `./scripts/validate_repo.sh workstream-surfaces` is expected to fail on this archived integration branch because the branch itself is no longer represented in `workstreams.yaml`; rerun that gate on `main` after merge

## Mainline Integration

- merged the exact-main replay back to `main` truth as repo version `0.178.126`
- updated ADR 0380 metadata to record the first merged repo version and the verified live platform version `0.178.78`
- archived the workstream shard after merge, while preserving the durable live-apply receipt `2026-04-12-adr-0380-neko-exact-main-live-apply` and supporting evidence under `receipts/live-applies/`
