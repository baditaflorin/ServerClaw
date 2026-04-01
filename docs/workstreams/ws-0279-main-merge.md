# Workstream ws-0279-main-merge

- ADR: [ADR 0279](../adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md)
- Title: Integrate ADR 0279 Grist exact-main replay onto `origin/main`
- Status: merged
- Included In Repo Version: 0.177.134
- Platform Version Observed During Integration: 0.130.84
- Release Date: 2026-04-01
- Live Applied On: 2026-04-01
- Branch: `codex/ws-0279-main-publish-r2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0279-main-publish-r1`
- Owner: codex
- Depends On: `ws-0279-live-apply`

## Purpose

Carry the verified ADR 0279 Grist work onto the newest merged `origin/main`,
rerun the exact-main live apply from the synchronized baseline, refresh the
protected release and canonical-truth surfaces from that result, and publish
the now-hardened Grist runtime plus its login-gated public surface on `main`.

## Current Continuation State

- The branch now carries the exact-main replay fix commit `c1c75d88d` on top
  of the latest fetched `origin/main` baseline `5e9cfe6e528a4261bddfb9430417daf80d5b3be0`
  (`0.177.133 / 0.130.83`).
- The April 1 replay succeeded from committed source on repository version
  `0.177.134` and advanced the integrated platform baseline to `0.130.84`.
- The earlier April 1 `r3` replay exposed a real automation defect in the new
  shared-edge discovery probe: the embedded Python assertion was malformed on
  the remote shell, which turned the readiness gate into an 18-retry failure.
- Commit `c1c75d88d` repaired that contract drift by replacing the inline
  Python one-liner with an environment-fed heredoc parser, adding explicit
  `curl` connect and total timeouts, and keeping the stricter blocked-login
  verification in both the startup and post-start recovery paths.
- The final `r4` replay proved both the pre-start discovery gate and the
  post-start OIDC bootstrap recovery path, including the targeted
  force-recreate of the `grist` container when the local auth surface still
  advertised `No login system is configured`.

## Shared Surfaces

- `Makefile`
- `README.md`
- `RELEASE.md`
- `VERSION`
- `changelog.md`
- `versions/stack.yaml`
- `build/platform-manifest.json`
- `workstreams.yaml`
- `docs/workstreams/ws-0279-main-merge.md`
- `docs/workstreams/ws-0279-live-apply.md`
- `docs/adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md`
- `docs/adr/.index.yaml`
- `docs/runbooks/configure-grist.md`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `playbooks/grist.yml`
- `playbooks/services/grist.yml`
- `collections/ansible_collections/lv3/platform/roles/grist_runtime/`
- `collections/ansible_collections/lv3/platform/roles/docker_runtime/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runner/`
- `collections/ansible_collections/lv3/platform/roles/gitea_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `collections/ansible_collections/lv3/platform/roles/lago_postgres/`
- `collections/ansible_collections/lv3/platform/roles/lago_runtime/`
- `collections/ansible_collections/lv3/platform/roles/langfuse_runtime/`
- `collections/ansible_collections/lv3/platform/roles/mail_platform_runtime/`
- `collections/ansible_collections/lv3/platform/roles/ollama_runtime/`
- `collections/ansible_collections/lv3/platform/roles/outline_runtime/`
- `collections/ansible_collections/lv3/platform/roles/proxmox_tailscale_proxy/`
- `collections/ansible_collections/lv3/platform/roles/restic_config_backup/`
- `collections/ansible_collections/lv3/platform/roles/typesense_runtime/`
- `collections/ansible_collections/lv3/platform/roles/common/tasks/docker_bridge_chains.yml`
- `config/ansible-execution-scopes.yaml`
- `config/subdomain-catalog.json`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/image-catalog.json`
- `config/certificate-catalog.json`
- `config/api-gateway-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/service-completeness.json`
- `config/service-redundancy-catalog.json`
- `config/grafana/dashboards/grist.json`
- `config/grafana/dashboards/slo-overview.json`
- `config/alertmanager/rules/grist.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/uptime-kuma/monitors.json`
- `config/subdomain-exposure-registry.json`
- `docs/release-notes/README.md`
- `docs/release-notes/*.md`
- `docs/diagrams/agent-coordination-map.excalidraw`
- `docs/diagrams/service-dependency-graph.excalidraw`
- `docs/site-generated/architecture/dependency-graph.md`
- `receipts/image-scans/2026-03-30-grist-runtime.json`
- `receipts/image-scans/2026-03-30-grist-runtime.trivy.json`
- `receipts/live-applies/2026-03-30-adr-0279-grist-live-apply.json`
- `receipts/live-applies/2026-03-30-adr-0279-grist-mainline-live-apply.json`
- `receipts/live-applies/2026-03-31-adr-0279-grist-mainline-live-apply.json`
- `receipts/live-applies/2026-04-01-adr-0279-grist-mainline-live-apply.json`
- `receipts/live-applies/evidence/2026-03-30-adr-0279-*`
- `receipts/live-applies/evidence/2026-03-31-adr-0279-*`
- `receipts/live-applies/evidence/2026-03-31-ws-0279-mainline-*`
- `receipts/live-applies/evidence/2026-04-01-ws-0279-*`
- `receipts/restic-backups/20260401T*.json`
- `receipts/restic-snapshots-latest.json`

## Verification

- `git fetch origin main` confirmed the latest realistic shared baseline before
  the final replay was commit `5e9cfe6e528a4261bddfb9430417daf80d5b3be0`
  (`0.177.133 / 0.130.83`).
- The focused Grist validation slice now returns `9 passed` across
  `tests/test_grist_runtime_role.py` and `tests/test_grist_playbook.py`, while
  `ansible-playbook -i inventory/hosts.yml playbooks/grist.yml --syntax-check`,
  `./scripts/validate_repo.sh agent-standards`,
  `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`,
  and `uv run --with pyyaml python scripts/generate_slo_rules.py --check` all
  passed on the integrated tree.
- The final governed replay in
  `receipts/live-applies/evidence/2026-04-01-ws-0279-grist-mainline-live-apply-r4-0.177.134.txt`
  ended with final recap
  `docker-runtime-lv3 : ok=309 changed=2 unreachable=0 failed=0 skipped=129`,
  `nginx-lv3 : ok=46 changed=4 unreachable=0 failed=0 skipped=7`, and
  `localhost : ok=24 changed=0 unreachable=0 failed=0 skipped=7`.
- That replay records the shared-edge discovery gate succeeding before Grist
  startup, the local blocked-login probe detecting the OIDC bootstrap gap, the
  targeted `grist` force-recreate after rediscovery, and both the local plus
  public login-gating assertions passing afterward.
- Fresh post-success proofs on 2026-04-01 reconfirm
  `https://grist.lv3.org/status` returning the canonical alive string,
  `https://grist.lv3.org/o/docs/` returning `HTTP/2 302` into the Keycloak
  auth flow, and the runtime logs advertising
  `OIDCConfig: initialized with issuer https://sso.lv3.org/realms/lv3` plus
  `loginMiddlewareComment: oidc`.
- `receipts/live-applies/2026-04-01-adr-0279-grist-mainline-live-apply.json`
  now records the canonical latest-main receipt for ADR 0279, while the March
  30 and March 31 receipts remain preserved as audit history.

## Outcome

- Release `0.177.134` now carries ADR 0279 onto the latest shared mainline
  baseline of `0.177.133 / 0.130.83`.
- The April 1 latest-main replay refreshed the Grist runtime and login-gated
  public surface, proved the automated OIDC bootstrap recovery contract on the
  shared docker-runtime guest, and advances the tracked integrated platform
  baseline to `0.130.84`.
- `receipts/live-applies/2026-04-01-adr-0279-grist-mainline-live-apply.json`
  is now the canonical mainline receipt for ADR 0279; the earlier branch-local
  receipt on `0.130.60` plus the March 30 and March 31 mainline replays remain
  part of the audit trail.
