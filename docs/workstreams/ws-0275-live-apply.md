# Workstream ws-0275-live-apply: ADR 0275 Live Apply From Latest `origin/main`

- ADR: [ADR 0275](../adr/0275-apache-tika-server-for-document-text-extraction-in-the-rag-pipeline.md)
- Title: private Apache Tika document extraction service live apply
- Status: in_progress
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: N/A
- Implemented On: N/A
- Live Applied On: N/A
- Branch: `codex/ws-0275-live-apply-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0275-live-apply-r2`
- Owner: codex
- Depends On: `adr-0023-docker-runtime-vm-baseline`, `adr-0067-guest-network-policy-enforcement`, `adr-0153-distributed-resource-lock-registry`, `adr-0191-immutable-guest-replacement`, `adr-0198-qdrant-vector-search-semantic-rag`, `adr-0263-qdrant-postgresql-and-local-search-as-the-serverclaw-memory-substrate`, `adr-0274-minio-as-the-s3-compatible-object-storage-layer`
- Conflicts With: none
- Shared Surfaces: `workstreams.yaml`, `docs/workstreams/ws-0275-live-apply.md`, `docs/adr/0275-apache-tika-server-for-document-text-extraction-in-the-rag-pipeline.md`, `docs/runbooks/configure-tika.md`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `scripts/generate_platform_vars.py`, `Makefile`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/image-catalog.json`, `config/service-completeness.json`, `config/service-redundancy-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/command-catalog.json`, `config/workflow-catalog.json`, `config/ansible-execution-scopes.yaml`, `config/grafana/dashboards/tika.json`, `config/alertmanager/rules/tika.yml`, `playbooks/tika.yml`, `playbooks/services/tika.yml`, `collections/ansible_collections/lv3/platform/playbooks/tika.yml`, `collections/ansible_collections/lv3/platform/roles/tika_runtime/`, `tests/test_tika_runtime_role.py`, `tests/test_tika_playbook.py`, `tests/test_generate_platform_vars.py`, `receipts/image-scans/`, `receipts/live-applies/`, `docs/adr/.index.yaml`

## Scope

- add the repo-managed private Apache Tika runtime, firewall exposure, health probes, dashboard, alerting, redundancy, SLO, and data-catalog surfaces
- live-apply the service from an isolated latest-main worktree, verify `/version`, `/tika`, and `/meta` end to end, and record merge-safe receipts plus ADR metadata
- finish this thread by carrying the verified change through exact-main integration and the protected release surfaces on `origin/main`

## Non-Goals

- publishing Apache Tika through the shared API gateway or the public edge
- adding OCR or the `-full` image variant; ADR 0275 explicitly keeps image-based OCR out of scope
- wiring every downstream caller to use Tika in this workstream; this change establishes the governed extraction service itself

## Expected Repo Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0275-live-apply.md`
- `docs/adr/0275-apache-tika-server-for-document-text-extraction-in-the-rag-pipeline.md`
- `docs/runbooks/configure-tika.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `Makefile`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/grafana/dashboards/slo-overview.json`
- `config/uptime-kuma/monitors.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/grafana/dashboards/tika.json`
- `config/alertmanager/rules/tika.yml`
- `playbooks/tika.yml`
- `playbooks/services/tika.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tika.yml`
- `collections/ansible_collections/lv3/platform/roles/tika_runtime/`
- `tests/test_tika_runtime_role.py`
- `tests/test_tika_playbook.py`
- `tests/test_generate_platform_vars.py`
- `receipts/image-scans/2026-03-30-tika-runtime.json`
- `receipts/image-scans/2026-03-30-tika-runtime.trivy.json`
- `receipts/live-applies/2026-03-30-adr-0275-apache-tika-live-apply.json`

## Expected Live Surfaces

- `docker-runtime-lv3` listens on `10.10.10.20:9998` for the private Apache Tika runtime
- `/opt/tika/docker-compose.yml` exists on `docker-runtime-lv3`
- the `tika` container is running on `docker-runtime-lv3`
- `GET /version`, `PUT /tika`, and `PUT /meta` succeed on the guest-local listener
- the service remains private to the guest network and local Docker callers only

## Ownership Notes

- `docker-runtime-lv3` is governed by ADR 0191 immutable guest replacement, so any in-place apply in this workstream is a narrow documented exception for the live replay
- the resource lock for this replay should be taken on `vm:120/service:tika` before mutation starts
- protected integration files remain out of scope until the final exact-main merge step in this same thread

## Verification

- `make ensure-resource-lock-registry`
- `python3 scripts/resource_lock_tool.py acquire --resource vm:120/service:tika --holder agent:codex/ws-0275-live-apply-r2 --lock-type exclusive --ttl-seconds 7200 --context-id ws-0275-live-apply`
- `uv run --with pytest --with pyyaml python -m pytest -q tests/test_tika_runtime_role.py tests/test_tika_playbook.py tests/test_generate_platform_vars.py tests/test_service_id_resolver.py`
- `make syntax-check-tika`
- `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0275syntax1 --playbook playbooks/services/tika.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check`
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=tika env=production EXTRA_ARGS='-e bypass_promotion=true'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 ops@100.64.0.1 -W %h:%p" ops@10.10.10.20 'curl -fsS http://127.0.0.1:9998/version'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 ops@100.64.0.1 -W %h:%p" ops@10.10.10.20 'printf "<html><body><h1>LV3 Tika runbook</h1></body></html>" | curl -fsS -X PUT -H "Content-Type: text/html" -H "Accept: text/plain" --data-binary @- http://127.0.0.1:9998/tika'`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5 ops@100.64.0.1 -W %h:%p" ops@10.10.10.20 'printf "<html><body><h1>LV3 Tika runbook</h1></body></html>" | curl -fsS -X PUT -H "Content-Type: text/html" -H "Accept: application/json" --data-binary @- http://127.0.0.1:9998/meta'`
