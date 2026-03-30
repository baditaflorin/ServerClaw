# Workstream ws-0287-live-apply: ADR 0287 Live Apply From Latest `origin/main`

- ADR: [ADR 0287](../adr/0287-woodpecker-ci-as-the-api-driven-continuous-integration-server.md)
- Title: deploy Woodpecker CI as the API-driven continuous integration server
- Status: live_applied
- Included In Repo Version: 0.177.110
- Branch-Local Receipt: `receipts/live-applies/2026-03-30-adr-0287-woodpecker-live-apply.json`
- Canonical Mainline Receipt: `receipts/live-applies/2026-03-30-adr-0287-woodpecker-mainline-live-apply.json`
- Live Applied In Platform Version: 0.130.73
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0287-mainline-final`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0287-mainline-final`
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

- The branch-local converge from the latest realistic `origin/main`
  baseline is recorded in
  `receipts/live-applies/2026-03-30-adr-0287-woodpecker-live-apply.json`.
- The first exact-main integration replay on the `0.177.110 / 0.130.72`
  candidate succeeded and is preserved in the `r1` evidence bundle under
  `receipts/live-applies/evidence/2026-03-30-ws-0287-mainline-r1-*`.
- When `origin/main` advanced during the exact-main rebase, the replay lost
  Woodpecker's controller-local secret manifest and several catalog entries.
  The correction loop is preserved in the `r2` through `r5` evidence files:
  the first focused pytest slice and `live-apply-service` preflight failed on
  the same missing catalog surfaces, the recovery restored the missing
  Woodpecker catalog and controller-local secret entries, refreshed
  `config/uptime-kuma/monitors.json`, added the already-merged Directus roles
  to `config/ansible-role-idempotency.yml`, and then re-ran the exact-main
  validation lane cleanly.
- The repaired exact-main candidate commit
  `cbc004fd0ae22cb6ed692430438ad5f31c24458b` now has a passing focused
  Woodpecker regression slice in
  `receipts/live-applies/evidence/2026-03-30-ws-0287-mainline-r5-targeted-checks-0.177.110.txt`
  with `123 passed in 9.24s`, and
  `make syntax-check-woodpecker` passed again in
  `receipts/live-applies/evidence/2026-03-30-ws-0287-mainline-r4-syntax-check-0.177.110.txt`.
- The final exact-main repository automation sweep also passed in the `r6`
  evidence bundle: live-apply receipt validation, repository data-model
  validation, `git diff --check`, `./scripts/validate_repo.sh
  agent-standards workstream-surfaces health-probes generated-docs
  data-models`, `make remote-validate`, and the full `make pre-push-gate`
  lane all completed successfully after refreshing the generated canonical
  truth and subdomain exposure registry.
- The repaired exact-main replay
  `ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=woodpecker env=production EXTRA_ARGS='-e bypass_promotion=true'`
  succeeded in
  `receipts/live-applies/evidence/2026-03-30-ws-0287-mainline-r3-live-apply-service-0.177.110.txt`
  with final recap `docker-runtime-lv3 : ok=157 changed=4 failed=0`,
  `nginx-lv3 : ok=47 changed=6 failed=0`, `postgres-lv3 : ok=51 changed=0 failed=0`,
  `proxmox_florin : ok=277 changed=1 failed=0`, and `localhost : ok=4 changed=0 failed=0`.
- Public and controller-local verification passed after the repaired exact-main
  replay: `https://ci.lv3.org/healthz` returned `HTTP/2 200` with
  `x-woodpecker-version: 3.13.0`, `http://100.64.0.1:8017/healthz` returned
  `HTTP/1.1 200 OK`, the TLS certificate remained `CN=ci.lv3.org` from Let's
  Encrypt `CN=E7`, `make woodpecker-manage ACTION=whoami` resolved to
  `ops-gitea`, and `make woodpecker-manage ACTION=list-secrets
  WOODPECKER_ARGS='--repo ops/proxmox_florin_server'` still exposed
  `LV3_WOODPECKER_SECRET_SMOKE`.

## Mainline Closeout

- The branch-local receipt remains the first-live audit trail for ADR 0287 on
  platform version `0.130.72`.
- The canonical mainline receipt
  `receipts/live-applies/2026-03-30-adr-0287-woodpecker-mainline-live-apply.json`
  carries the repaired exact-main replay onto repo version `0.177.110` and
  platform version `0.130.73`.
- The final post-push `main` pipeline trigger proof is attached to the
  canonical mainline receipt so the workstream branch remains a stable audit
  trail while the integrated `main` closeout records the forge-visible proof.
