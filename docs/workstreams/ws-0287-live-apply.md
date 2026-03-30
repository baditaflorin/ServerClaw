# Workstream ws-0287-live-apply: ADR 0287 Live Apply From Latest `origin/main`

- ADR: [ADR 0287](../adr/0287-woodpecker-ci-as-the-api-driven-continuous-integration-server.md)
- Title: deploy Woodpecker CI as the API-driven continuous integration server
- Status: ready_for_merge
- Branch: `codex/ws-0287-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0287-live-apply`
- Owner: codex
- Depends On: `adr-0042`, `adr-0077`, `adr-0107`, `adr-0143`
- Conflicts With: none

## Scope

- add the repo-managed Woodpecker server and agent on `docker-runtime-lv3`
- provision the dedicated PostgreSQL database, Gitea OAuth bootstrap, OpenBao-backed runtime secrets, and `ci.lv3.org` edge publication
- define the repository-root `.woodpecker.yml` validation pipeline and seed the `ops/proxmox_florin_server` repository activation plus CI smoke secret through the Woodpecker API
- live-apply the change from this isolated latest-main worktree, verify the API-driven workflow end to end, and leave merge-safe receipts plus ADR metadata behind

## Shared Surfaces

- `workstreams.yaml`
- `docs/workstreams/ws-0287-live-apply.md`
- `docs/adr/0287-woodpecker-ci-as-the-api-driven-continuous-integration-server.md`
- `docs/runbooks/configure-woodpecker.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `scripts/generate_platform_vars.py`
- `playbooks/woodpecker.yml`
- `playbooks/services/woodpecker.yml`
- `collections/ansible_collections/lv3/platform/playbooks/woodpecker.yml`
- `collections/ansible_collections/lv3/platform/roles/woodpecker_postgres/`
- `collections/ansible_collections/lv3/platform/roles/woodpecker_runtime/`
- `platform/ansible/woodpecker.py`
- `scripts/woodpecker_bootstrap.py`
- `scripts/woodpecker_tool.py`
- `.woodpecker.yml`
- `config/api-gateway-catalog.json`
- `config/certificate-catalog.json`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/image-catalog.json`
- `config/service-completeness.json`
- `config/subdomain-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/dependency-graph.json`
- `config/service-redundancy-catalog.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/command-catalog.json`
- `config/workflow-catalog.json`
- `config/ansible-execution-scopes.yaml`
- `config/ansible-role-idempotency.yml`
- `config/correction-loops.json`
- `config/subdomain-exposure-registry.json`
- `config/uptime-kuma/monitors.json`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/grafana/dashboards/slo-overview.json`
- `Makefile`
- `playbooks/tasks/post-verify.yml`
- `collections/ansible_collections/lv3/platform/playbooks/tasks/post-verify.yml`
- `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/`
- `tests/test_generate_platform_vars.py`
- `tests/test_nginx_edge_publication_role.py`
- `tests/test_post_verify_tasks.py`
- `tests/test_postgres_vm_access_policy.py`
- `tests/test_temporal_playbook.py`
- `tests/test_woodpecker_client.py`
- `tests/test_woodpecker_playbook.py`
- `tests/test_woodpecker_runtime_role.py`
- `tests/test_woodpecker_tool.py`
- `receipts/image-scans/`
- `receipts/live-applies/`
- `docs/adr/.index.yaml`

## Verification

- `make validate-generated-vars`
- `make syntax-check-woodpecker`
- `uv tool run --from ansible-lint ansible-lint playbooks/woodpecker.yml playbooks/services/woodpecker.yml collections/ansible_collections/lv3/platform/roles/woodpecker_postgres collections/ansible_collections/lv3/platform/roles/woodpecker_runtime collections/ansible_collections/lv3/platform/playbooks/woodpecker.yml`
- `./scripts/validate_repo.sh json health-probes data-models agent-standards`
- `uv run --with pytest --with pyyaml --with jsonschema python -m pytest tests/test_generate_platform_vars.py tests/test_postgres_vm_access_policy.py tests/test_woodpecker_playbook.py tests/test_woodpecker_runtime_role.py tests/test_woodpecker_client.py tests/test_validate_service_catalog.py tests/test_validate_service_completeness.py tests/test_subdomain_catalog.py tests/test_service_redundancy.py tests/test_workstream_surface_ownership.py tests/test_ansible_execution_scopes.py tests/test_ansible_role_idempotency.py tests/test_data_catalog.py tests/test_subdomain_exposure_audit.py -q`
- `HETZNER_DNS_API_TOKEN=... make converge-woodpecker env=production` completed successfully on replay `r14`, converging the Proxmox proxy lane, PostgreSQL access, Woodpecker runtime, `ci.lv3.org` edge publication, a dedicated `ci.lv3.org` Let's Encrypt certificate, and the controller-local bootstrap artifacts plus seed repository secret.
- `curl -fsS http://100.64.0.1:8017/healthz`
- `curl -fsSI https://ci.lv3.org/healthz`
- `openssl s_client -connect ci.lv3.org:443 -servername ci.lv3.org </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -ext subjectAltName`
- `make woodpecker-manage ACTION=whoami`
- `make woodpecker-manage ACTION=list-secrets WOODPECKER_ARGS='--repo ops/proxmox_florin_server'`

## Live Apply State

- Latest realistic upstream is `origin/main` commit `456984e2ebfed2f7d154c16dc1f49be79731520e`, which currently carries `VERSION` `0.177.109` and platform baseline `0.130.72`.
- The successful branch-local replay is recorded in `receipts/live-applies/evidence/2026-03-30-ws-0287-live-apply-r14.txt`.
- The public edge role now falls back to a dedicated site-local certificate for `ci.lv3.org` when the shared `lv3-edge` certificate does not yet cover the Woodpecker hostname, so unrelated SAN churn on the shared edge certificate no longer blocks the live apply.
- The controller-local Woodpecker API bundle is verified live: `whoami` resolves to `ops-gitea` admin user `id=1`, and the seeded repository secret list contains `LV3_WOODPECKER_SECRET_SMOKE`.
- Manual `trigger-pipeline --branch main --wait` is not yet a valid exact-main verification on this branch because `origin/main` still does not contain `.woodpecker.yml`; Woodpecker accepts the trigger request with `204 No Content`, but no pipeline becomes visible until the forge branch being triggered actually carries the workflow file.
- `workstreams.yaml` stays non-terminal on this branch so branch-level ownership validation remains active until the final `main` closeout flips the workstream back to its terminal state.
- Rebasing onto `456984e2ebfed2f7d154c16dc1f49be79731520e` required regenerating `config/subdomain-exposure-registry.json`; the rebased branch-side `workstream-surfaces` and `data-models` checks now pass again on top of that latest mainline snapshot.

## Remaining For Merge-To-Main

- Do not update `VERSION`, release sections in `changelog.md`, the top-level integrated `README.md` summary, or `versions/stack.yaml` on this branch.
- The protected integration files still must wait for the final exact-main replay from the latest `origin/main`.
- This branch is already rebased onto `origin/main` commit `456984e2ebfed2f7d154c16dc1f49be79731520e`; pull again before the final `main` push in case newer mainline work lands.
- Update `VERSION`, the release notes in `changelog.md`, the top-level `README.md` integrated truth, and `versions/stack.yaml` only on the final mainline integration step.
- After the mainline commit is pushed and the forge branch being tested contains `.woodpecker.yml`, rerun `make woodpecker-manage ACTION=trigger-pipeline WOODPECKER_ARGS='--repo ops/proxmox_florin_server --branch main --wait'` and record the exact-main verification receipt.
