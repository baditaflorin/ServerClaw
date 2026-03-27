# Workstream ws-0101-live-apply: ADR 0101 Live Apply From Latest `origin/main`

- ADR: [ADR 0101](../adr/0101-automated-certificate-lifecycle-management.md)
- Title: live replay, recovery, validation, and evidence capture for automated certificate lifecycle management
- Status: live_applied
- Branch: `codex/ws-0101-live-apply`
- Worktree: `.worktrees/ws-0101-live-apply`
- Owner: codex
- Depends On: `adr-0101-certificate-lifecycle`
- Conflicts With: none
- Shared Surfaces: `playbooks/openbao.yml`, `roles/openbao_runtime`, `roles/vaultwarden_runtime`, `roles/cert_renewal_timer`, `config/certificate-catalog.json`, `docs/runbooks/configure-openbao.md`, `receipts/live-applies/`

## Scope

- replay the ADR 0101 runtime from the latest `origin/main` in an isolated worktree
- verify the live OpenBao and Vaultwarden renewal timers plus the host Tailscale proxy paths
- validate the repository data-model and probe automation paths after the live replay
- record the live recovery steps and any remaining merge-to-`main` integration work without touching protected integration files on this branch

## Verification

- `uv run --with pytest python -m pytest tests/test_tls_cert_probe.py tests/test_generate_cert_renewal_config.py tests/test_tls_cert_drift.py tests/test_platform_observation_tool.py tests/test_compose_runtime_secret_injection.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `python3 scripts/generate_cert_renewal_config.py --pretty`
- `make syntax-check-openbao`
- `make syntax-check-step-ca`
- `make converge-openbao`
- `make converge-step-ca`
- `python3 scripts/tls_cert_probe.py --certificate-id openbao-proxy --fail-on never`
- `python3 scripts/tls_cert_probe.py --certificate-id vaultwarden-private --fail-on never`
- `python3 scripts/tls_cert_probe.py --certificate-id step-ca-proxy --fail-on never`
- `curl --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt https://100.64.0.1:9443/health`
- `curl -vk https://100.64.0.1:8200/v1/sys/health`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -W %h:%p ops@100.64.0.1' ops@10.10.10.20 'systemctl status lv3-openbao-cert-renew.timer lv3-vaultwarden-cert-renew.timer --no-pager'`

## Outcome

- The live replay started from `origin/main` commit `9457e4694f5a80b8876ff4e99e400b6960a07cb7` in repo release context `0.174.0`.
- The follow-up repo fixes removed `postgres-replica-lv3` from the active `production` inventory target set, and a fresh `make converge-openbao` completed successfully against `postgres-lv3` and `docker-runtime-lv3` without reintroducing the stale replica path.
- The OpenBao and step-ca runtime roles now self-heal the recurring Docker NAT-chain drift on `docker-runtime-lv3` by rechecking `DOCKER` and `DOCKER-FORWARD`, restarting Docker when needed, and recreating broken published-port containers before compose startup.
- `lv3-openbao-cert-renew.timer` and `lv3-vaultwarden-cert-renew.timer` are active on `docker-runtime-lv3`, and the host-side `lv3-tailscale-proxy-openbao` and `lv3-tailscale-proxy-step-ca` socket/service pairs are active on `proxmox_florin`.
- The step-ca replay now keeps `ca.json` server names aligned with the current controller topology, starts the container with `STEPPATH=/opt/step-ca/home`, and removes the misplaced guest-firewall role from the Proxmox-host SSH trust play so `make converge-step-ca` completes end to end.
- The probe contract now validates `step-ca` endpoints from git worktrees, models short-lived 24-hour certificates with hour-based warning windows, probes Vaultwarden through the host Tailscale IP with `vault.lv3.org` SNI, and uses a corrected readiness command for `step-ca`.
- `openbao-proxy` probes cleanly with `status: ok`; `vaultwarden-private` is reachable through `curl --resolve vault.lv3.org:443:100.64.0.1 https://vault.lv3.org/`; and `curl --cacert ... https://100.64.0.1:9443/health` now succeeds directly against `step-ca-proxy` without the legacy SAN workaround.
- The final `main` integration replay on `2026-03-27` completed with `make converge-step-ca`, `make converge-vaultwarden`, and `make converge-openbao` all passing after adding an SSH reconnect guard to the `step_ca_runtime` verification path and bounded retries around the flakiest `openbao_runtime` mutation calls.
- The canonical release and live state are now advanced on `main` in repo version `0.176.8` and platform version `0.130.24`, with the verified replay recorded in `receipts/live-applies/2026-03-27-adr-0101-certificate-lifecycle-main-live-apply.json`.

## Remaining For Merge To `main`

- None. The protected integration files were updated during the final mainline release step on `2026-03-27`.
