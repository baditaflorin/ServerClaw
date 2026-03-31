# Workstream ws-0291-main-merge

- ADR: [ADR 0291](../adr/0291-jupyterhub-as-the-interactive-notebook-environment.md)
- Title: Integrate ADR 0291 JupyterHub exact-main replay onto `origin/main`
- Status: merged
- Included In Repo Version: 0.177.111
- Platform Version Observed During Integration: 0.130.73
- Release Date: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0291-main-merge`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0291-main-merge`
- Owner: codex
- Depends On: `ws-0291-live-apply`

## Purpose

Carry the verified ADR 0291 JupyterHub live-apply branch onto the newest
available `origin/main`, rerun the exact-main notebook replay from committed
source on that synchronized baseline, cut the protected release and
canonical-truth surfaces from the resulting tree, and publish the JupyterHub
notebook environment on `main` with current live evidence instead of relying on
branch-local state alone.

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0291-main-merge.md`
- `docs/workstreams/ws-0291-live-apply.md`
- `docs/adr/0291-jupyterhub-as-the-interactive-notebook-environment.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-jupyterhub.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `Makefile`
- `scripts/tofu_exec.sh`
- `scripts/validate_repo.sh`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/api-gateway-catalog.json`
- `config/certificate-catalog.json`
- `config/service-completeness.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/service-redundancy-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/subdomain-catalog.json`
- `config/subdomain-exposure-registry.json`
- `config/uptime-kuma/monitors.json`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/grafana/dashboards/slo-overview.json`
- `config/workflow-catalog.json`
- `config/command-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `playbooks/jupyterhub.yml`
- `playbooks/services/jupyterhub.yml`
- `collections/ansible_collections/lv3/platform/roles/jupyterhub_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/defaults/main.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/tasks/main.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_systemd_credentials.yml`
- `collections/ansible_collections/lv3/platform/roles/ollama_runtime/`
- `tests/test_generate_platform_vars.py`
- `tests/test_jupyterhub_runtime_role.py`
- `tests/test_jupyterhub_playbook.py`
- `tests/test_keycloak_runtime_role.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_ollama_runtime_role.py`
- `tests/test_openbao_compose_env_helper.py`
- `tests/test_edge_publication_makefile.py`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/ops-portal-snapshot.html`
- `receipts/live-applies/2026-03-30-adr-0291-jupyterhub-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0291-jupyterhub-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-ws-0291-*`

## Verification

- `git fetch origin --prune` refreshed this workstream onto the newer
  `origin/main` commit `456984e2e2d0c8e5ca32c8d652ecf154961f4f22`, which already
  carried the Flagsmith exact-main closeout on top of repo version `0.177.109`
  and platform version `0.130.72` before the JupyterHub integration work
  continued.
- The focused exact-main compatibility slice reran successfully on that rebased
  tree with `73 passed in 4.49s`, plus `make syntax-check-jupyterhub`,
  `make syntax-check-ollama`, and
  `python3 scripts/validate_service_completeness.py --service jupyterhub`;
  the full transcript is preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-targeted-checks-r2.txt`.
- The first exact-main wrapper attempt exposed a missing
  `keycloak_jupyterhub_client_secret` catalog entry after the rebase and the
  second stopped at the expected canonical-truth guard before the release tree
  was written; those repair steps are preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-live-apply-r1.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-portal-generators-r1.txt`,
  and `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-live-apply-r2.txt`.
- `LV3_SKIP_OUTLINE_SYNC=1 uv run --with pyyaml python scripts/release_manager.py ...`
  prepared release `0.177.110` while preserving `platform_version: 0.130.72`,
  preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-release-status-r2.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-release-dry-run-r1.txt`,
  and `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-release-write-r1.txt`.
- `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=jupyterhub env=production`
  succeeded from committed source `2d53cf4eeaaa3da136eef6d44f79d7393f6329c3`
  with final recap `docker-runtime-lv3 : ok=278 changed=5 failed=0 skipped=82`,
  `localhost : ok=24 changed=0 failed=0 skipped=4`, and
  `nginx-lv3 : ok=40 changed=5 failed=0 skipped=6`, preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-live-apply-r4.txt`.
- Fresh controller verification after the exact-main replay confirmed the
  public health endpoint, the Keycloak OIDC redirect, the shared edge
  certificate SAN set including `DNS:notebooks.lv3.org` and
  `DNS:flags.lv3.org`, and the local `docker-runtime-lv3` JupyterHub, Ollama,
  and platform-context probes,
  preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-direct-verification-r3.txt`.
- Final repo automation and validation gates passed from the detached exact-main
  tree, including `make check-build-server`, `make validate`,
  `make remote-validate`, `make pre-push-gate`,
  `python scripts/live_apply_receipts.py --validate`, and `git diff --check`,
  preserved in
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-check-build-server-r2.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-validate-r4.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-remote-validate-r4.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-pre-push-gate-r2.txt`,
  `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-live-apply-receipts-validate-r3.txt`,
  and `receipts/live-applies/evidence/2026-03-30-ws-0291-mainline-git-diff-check-r3.txt`.

## Outcome

- Release `0.177.111` is the integrated repo version for ADR 0291.
- Platform version remains `0.130.73` because the notebook environment first
  became true on `0.130.71`; the exact-main replay verifies that already-live
  capability on the newer synchronized baseline instead of advancing the
  platform version again.
- `receipts/live-applies/2026-03-30-adr-0291-jupyterhub-mainline-live-apply.json`
  is the canonical exact-main proof for JupyterHub on `main`.
