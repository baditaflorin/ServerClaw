# Workstream ws-0279-live-apply: Live Apply ADR 0279 From Latest `origin/main`

- ADR: [ADR 0279](../adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md)
- Title: Deploy Grist on `docker-runtime-lv3`, publish `grist.lv3.org`, and verify the OIDC-backed spreadsheet runtime end to end
- Status: ready_for_merge
- Implemented In Repo Version: N/A
- Live Applied In Platform Version: 0.130.60
- Implemented On: 2026-03-30
- Live Applied On: 2026-03-30
- Branch: `codex/ws-0279-live-apply`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/ws-0279-live-apply`
- Owner: codex
- Depends On: `adr-0063-keycloak-sso`, `adr-0086-backup-and-recovery`, `adr-0191-immutable-guest-replacement`, `adr-0279-grist-as-the-no-code-operational-spreadsheet-database`
- Conflicts With: none
- Shared Surfaces: `docs/adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md`, `docs/workstreams/ws-0279-live-apply.md`, `docs/runbooks/configure-grist.md`, `playbooks/grist.yml`, `playbooks/services/grist.yml`, `collections/ansible_collections/lv3/platform/roles/grist_runtime/`, `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`, `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `config/subdomain-catalog.json`, `config/service-capability-catalog.json`, `config/health-probe-catalog.json`, `config/secret-catalog.json`, `config/controller-local-secrets.json`, `config/image-catalog.json`, `config/api-gateway-catalog.json`, `config/dependency-graph.json`, `config/slo-catalog.json`, `config/data-catalog.json`, `config/service-completeness.json`, `config/grafana/dashboards/grist.json`, `config/alertmanager/rules/grist.yml`, `config/prometheus/file_sd/slo_targets.yml`, `config/prometheus/file_sd/https_tls_targets.yml`, `config/prometheus/rules/slo_rules.yml`, `config/prometheus/rules/slo_alerts.yml`, `config/prometheus/rules/https_tls_alerts.yml`, `config/uptime-kuma/monitors.json`, `config/subdomain-exposure-registry.json`, `receipts/image-scans/`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- add the repo-managed Grist runtime, Keycloak OIDC client, edge publication, and verification path for `grist.lv3.org`
- make Grist a first-class service across the repo catalogs, health probes, image policy, and validation surfaces
- perform the branch-local live apply from this isolated worktree and record the evidence clearly
- finish with the exact merge-to-main follow-through once the latest `origin/main` is synchronized

## Non-Goals

- introducing a separate Grist automation identity unless the live verification proves the existing named operator account is insufficient
- changing release-only truth surfaces on this branch before the final integrated `main` step
- expanding Grist into API-driven workflow bootstrap beyond the core runtime, OIDC, backup scope, and health verification required by ADR 0279

## Expected Repo Surfaces

- `docs/adr/0279-grist-as-the-no-code-operational-spreadsheet-database.md`
- `docs/workstreams/ws-0279-live-apply.md`
- `docs/runbooks/configure-grist.md`
- `playbooks/grist.yml`
- `playbooks/services/grist.yml`
- `collections/ansible_collections/lv3/platform/roles/grist_runtime/`
- `collections/ansible_collections/lv3/platform/roles/keycloak_runtime/`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `config/subdomain-catalog.json`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/secret-catalog.json`
- `config/controller-local-secrets.json`
- `config/image-catalog.json`
- `config/api-gateway-catalog.json`
- `config/dependency-graph.json`
- `config/slo-catalog.json`
- `config/data-catalog.json`
- `config/service-completeness.json`
- `config/grafana/dashboards/grist.json`
- `config/alertmanager/rules/grist.yml`
- `config/prometheus/file_sd/slo_targets.yml`
- `config/prometheus/file_sd/https_tls_targets.yml`
- `config/prometheus/rules/slo_rules.yml`
- `config/prometheus/rules/slo_alerts.yml`
- `config/prometheus/rules/https_tls_alerts.yml`
- `config/uptime-kuma/monitors.json`
- `config/subdomain-exposure-registry.json`
- `tests/test_grist_runtime_role.py`
- `tests/test_grist_playbook.py`
- `tests/test_keycloak_runtime_role.py`
- `workstreams.yaml`

## Expected Live Surfaces

- `docker-runtime-lv3` runs the repo-managed Grist container on the declared listener with persistent document storage
- `grist.lv3.org` resolves through the shared NGINX edge and delegates sign-in to the repo-managed Keycloak OIDC client
- the first administrator path is governed by the named Keycloak operator identity declared in repo automation
- Grist document storage is included in the declared runtime data and backup scope

## Ownership Notes

- this workstream owns the ADR 0279 live-apply implementation, verification evidence, and exact merge-to-main follow-through
- because `docker-runtime-lv3` is governed by ADR 0191 immutable guest replacement, any in-place production replay must keep the documented narrow exception explicit
- if the branch-local live apply finishes before the final integrated `main` replay, the handoff must state exactly which protected truth surfaces remain to be updated on `main`

## Verification

- `python3 scripts/validate_service_completeness.py --service grist`
- `uv run --with pytest python -m pytest -q tests/test_grist_runtime_role.py tests/test_grist_playbook.py tests/test_keycloak_runtime_role.py tests/test_validate_service_completeness.py`
- `make generate-slo-rules generate-https-tls-assurance generate-uptime-kuma-monitors`
- `uvx --from pyyaml python scripts/subdomain_exposure_audit.py --write-registry`
- `./scripts/validate_repo.sh agent-standards`
- `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0279syntax --playbook playbooks/services/grist.yml --env production -- --private-key .local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check`
- branch-local live apply from this worktree via the direct scoped runner if `make live-apply-service` is still blocked by protected canonical-truth surfaces
- exact-main live apply through `make live-apply-service service=grist env=production` once the workstream is integrated onto the latest synchronized `main`

## Live Apply Outcome

- `python3 scripts/validate_service_completeness.py --service grist` passed, and the focused regression slice across the Grist runtime, Grist playbooks, Keycloak integration, OpenBao compose-env helper, execution scopes, service completeness, subdomain exposure, and image-policy contracts returned `58 passed in 4.81s`.
- `./scripts/validate_repo.sh agent-standards workstream-surfaces data-models` passed after the workstream ownership manifest was narrowed to shared contracts for the common topology, catalog, generated portal, and OpenBao helper surfaces.
- `make preflight WORKFLOW=live-apply-service service=grist env=production`, `scripts/interface_contracts.py --check-live-apply service:grist`, `scripts/standby_capacity.py --service grist`, `scripts/service_redundancy.py --check-live-apply --service grist`, and `scripts/immutable_guest_replacement.py --check-live-apply --service grist --allow-in-place-mutation` all passed from this isolated worktree.
- `uv run --with pyyaml --with jsonschema python scripts/ansible_scope_runner.py run --inventory inventory/hosts.yml --run-id ws0279syntax2 --playbook playbooks/services/grist.yml --env production -- --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --syntax-check` passed.
- The scoped live apply completed successfully from this worktree with final recap `docker-runtime-lv3 ok=222 changed=16 failed=0`, `localhost ok=24 changed=0 failed=0`, and `nginx-lv3 ok=39 changed=5 failed=0`.
- The workstream fixed the production replay blocker exposed during the first attempt by teaching `collections/ansible_collections/lv3/platform/roles/common/tasks/openbao_compose_env.yml` to recover the local `lv3-openbao` container before waiting for the API; the rerun then completed cleanly through Keycloak secret injection, Grist secret injection, publication, and verification.

## Live Evidence

- `curl -fsS https://grist.lv3.org/status` returned `Grist server(home,docs,static) is alive.`.
- `curl -sSI https://grist.lv3.org/o/docs/` returned `HTTP/2 302` into the Keycloak realm on `https://sso.lv3.org/realms/lv3/...` with `client_id=grist` and the Grist callback redirect URI.
- `echo | openssl s_client -servername grist.lv3.org -connect grist.lv3.org:443 2>/dev/null | openssl x509 -noout -issuer -subject -ext subjectAltName` showed a Let's Encrypt issuer (`CN=E7`) and SAN coverage for `DNS:grist.lv3.org`.
- Controller-local secrets now exist at `.local/keycloak/grist-client-secret.txt` and `.local/grist/session-secret.txt`.
- Guest-local verification on `docker-runtime-lv3` confirmed `/opt/grist/docker-compose.yml`, `/opt/grist/openbao/agent.hcl`, and `/run/lv3-secrets/grist/runtime.env` are present, and `sudo docker ps --no-trunc` showed the `grist`, `grist-openbao-agent`, and `lv3-openbao` containers running.

## Manual Exception

- The first publication attempt failed during the hidden Hetzner DNS task before evidence could prove whether the DNS record had been created. To unblock the replay, the `grist` A record for `grist.lv3.org` was created manually through the Hetzner DNS API against `65.108.75.123`, returning record id `0b604871e23c549236e54742c5790ba8`.
- The successful scoped rerun then observed the record and completed idempotently through the repo-managed DNS and NGINX publication path. This exception is recorded in the branch-local live-apply receipt and must remain visible until the final `main` integration closes it out.

## Remaining For Mainline Integration

- Pull the newest `origin/main` again immediately before integration because concurrent work continued after this branch-local replay.
- Rebase or merge this workstream onto the latest `origin/main` without rewriting unrelated files, then rerun the exact-main Grist apply from the synchronized tree so the canonical receipt is based on `main`.
- Update only the protected mainline truth surfaces during that integration step: `VERSION`, `changelog.md`, `README.md`, `versions/stack.yaml`, release-note surfaces, and any generated canonical manifests that the release tooling refreshes.
- Replace the branch-local receipt `receipts/live-applies/2026-03-30-adr-0279-grist-live-apply.json` with the final exact-main receipt reference once the synchronized replay completes.

## Merge Criteria

- Grist is repo-managed as an OIDC-backed, stateful docker-runtime service instead of an undocumented ad hoc container
- the first verified live apply proves runtime availability, public publication, and browser sign-in delegation end to end
- ADR 0279 metadata records repository implementation plus the first verified platform version where the change is true
