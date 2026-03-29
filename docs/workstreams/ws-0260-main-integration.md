# Workstream ws-0260-main-integration

- ADR: [ADR 0260](../adr/0260-nextcloud-as-the-canonical-personal-data-plane-for-serverclaw.md)
- Title: Integrate ADR 0260 exact-main replay onto `origin/main`
- Status: `in_progress`
- Planned Repo Version: 0.177.87
- Target Platform Version: 0.130.59
- Branch: `codex/ws-0260-main-integration`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0260-main-integration`
- Owner: codex
- Depends On: `ws-0260-live-apply`

## Purpose

Carry the verified ADR 0260 Nextcloud personal data plane onto the latest
available `origin/main`, refresh the protected release and canonical-truth
surfaces from that merged baseline, rerun the exact-main Nextcloud replay on
the synchronized tree, and only then merge and push `main`.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0260-main-integration.md`
- `docs/workstreams/ws-0260-live-apply.md`
- `docs/adr/0260-nextcloud-as-the-canonical-personal-data-plane-for-serverclaw.md`
- `docs/adr/.index.yaml`
- `docs/adr/0094-developer-portal-and-documentation-site.md`
- `docs/runbooks/configure-nextcloud.md`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/0.177.87.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/site-generated/architecture/dependency-graph.md`
- `Makefile`
- `playbooks/docker-publication-assurance.yml`
- `playbooks/tasks/docker-publication-assert.yml`
- `playbooks/tasks/post-verify.yml`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `docs/runbooks/docker-publication-assurance.md`
- `docs/runbooks/health-probe-contracts.md`
- `docs/runbooks/playbook-execution-model.md`
- `docs/workstreams/adr-0270-docker-publication-self-healing-and-port-programming-assertions.md`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/docker-publication-assert.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/post-verify.yml`
- `scripts/generate_platform_vars.py`
- `scripts/docker_publication_assurance.py`
- `scripts/platform_observation_tool.py`
- `scripts/restore_verification.py`
- `scripts/validate_repository_data_models.py`
- `playbooks/nextcloud.yml`
- `playbooks/services/nextcloud.yml`
- `collections/ansible_collections/lv3/platform/playbooks/nextcloud.yml`
- `collections/ansible_collections/lv3/platform/playbooks/services/nextcloud.yml`
- `collections/ansible_collections/lv3/platform/plugins/filter/service_topology.py`
- `collections/ansible_collections/lv3/platform/roles/common/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/common/meta/argument_specs.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/meta/argument_specs.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/tasks/verify.yml`
- `collections/ansible_collections/lv3/platform/roles/linux_guest_firewall/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/nextcloud_postgres/**`
- `collections/ansible_collections/lv3/platform/roles/nextcloud_runtime/**`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/templates/lv3-edge.conf.j2`
- `config/alertmanager/rules/nextcloud.yml`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `config/capability-contract-catalog.json`
- `config/certificate-catalog.json`
- `config/command-catalog.json`
- `config/controller-local-secrets.json`
- `config/data-catalog.json`
- `config/dependency-graph.json`
- `config/grafana/dashboards/nextcloud.json`
- `config/grafana/dashboards/slo-overview.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/replaceability-review-catalog.json`
- `config/secret-catalog.json`
- `config/service-capability-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/slo-catalog.json`
- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/uptime-kuma/monitors.json`
- `config/workflow-catalog.json`
- `tests/test_docker_runtime_role.py`
- `tests/test_docker_publication_assurance.py`
- `tests/test_docker_publication_assurance_playbook.py`
- `tests/test_generate_platform_vars.py`
- `tests/test_interface_contracts.py`
- `tests/test_linux_guest_firewall_role.py`
- `tests/test_nextcloud_playbook.py`
- `tests/test_nextcloud_runtime_role.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_platform_observation_tool.py`
- `tests/test_postgres_vm_access_policy.py`
- `tests/test_post_verify_tasks.py`
- `tests/test_service_topology_filters.py`
- `receipts/image-scans/2026-03-29-nextcloud-runtime.json`
- `receipts/image-scans/2026-03-29-nextcloud-runtime.trivy.json`
- `receipts/image-scans/2026-03-29-nextcloud-redis-runtime.json`
- `receipts/image-scans/2026-03-29-nextcloud-redis-runtime.trivy.json`
- `receipts/live-applies/2026-03-29-adr-0260-nextcloud-personal-data-plane-mainline-live-apply.json`

## Plan

- refresh the protected version and README truth so repository version
  `0.177.87` and platform version `0.130.59` match the merged exact-main
  replay state
- regenerate ADR index, status docs, platform manifest, dependency graph, and
  any other derived artifacts touched by the final merge
- rerun the focused regression slice, `make converge-nextcloud`, and the
  public plus guest-local Nextcloud verification path from this synchronized
  integration worktree
- carry the Docker publication self-healing helper and contract wiring needed
  to recover host-side bridge/NAT loss that leaves `nextcloud-app` running
  without a published `8084` listener or container egress to Postgres
- run repository automation and validation gates end to end before merging to
  `main` and pushing `origin/main`

## Notes

- The latest merged baseline for this wrapper already includes ADR 0245's
  declared-to-live attestation rollout plus ADRs 0297 through 0306.
- `ws-0260-live-apply` preserves the branch-local implementation and receipt
  history; this wrapper owns the protected mainline recut and final push.
