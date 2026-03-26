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
- `python3 scripts/tls_cert_probe.py --certificate-id openbao-proxy --fail-on never`
- `python3 scripts/tls_cert_probe.py --certificate-id vaultwarden-private --fail-on never`
- `python3 scripts/tls_cert_probe.py --certificate-id step-ca-proxy --fail-on never`
- `curl --resolve 100.118.189.95:9443:100.64.0.1 --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/step-ca/certs/root_ca.crt https://100.118.189.95:9443/health`
- `curl -vk https://100.64.0.1:8200/v1/sys/health`
- `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -W %h:%p ops@100.64.0.1' ops@10.10.10.20 'systemctl status lv3-openbao-cert-renew.timer lv3-vaultwarden-cert-renew.timer --no-pager'`

## Outcome

- The live replay started from `origin/main` commit `9457e4694f5a80b8876ff4e99e400b6960a07cb7` in repo release context `0.174.0`.
- `make converge-openbao` exposed two live issues on the current platform: stale inventory still targeting `postgres-replica-lv3`, and an OpenBao Docker publish failure after firewall reload that left `lv3-openbao` detached from `openbao_default`.
- The production recovery succeeded by restarting Docker on `docker-runtime-lv3`, removing the broken `lv3-openbao` container, recreating `openbao_default`, bringing `/opt/openbao/docker-compose.yml` back up, and restarting the host-side `lv3-tailscale-proxy-openbao` socket pair.
- `lv3-openbao-cert-renew.timer` and `lv3-vaultwarden-cert-renew.timer` are active on `docker-runtime-lv3`, and the host-side `lv3-tailscale-proxy-openbao` and `lv3-tailscale-proxy-step-ca` socket/service pairs are active on `proxmox_florin`.
- The probe contract now validates `step-ca` endpoints from git worktrees, models short-lived 24-hour certificates with hour-based warning windows, and probes Vaultwarden through the host Tailscale IP with `vault.lv3.org` SNI so the controller no longer depends on local private DNS.
- `openbao-proxy` now probes cleanly with `status: ok` and `hours_remaining: 11`; `vaultwarden-private` is reachable through `curl --resolve vault.lv3.org:443:100.64.0.1 https://vault.lv3.org/`; `step-ca-proxy` still reports the existing SAN mismatch because the live proxy certificate does not yet cover `100.64.0.1`.

## Remaining For Merge To `main`

- Keep this branch’s protected integration files unchanged until the mainline integrator decides the release cut: `VERSION`, release sections in `changelog.md`, the top-level `README.md` integrated status summary, and `versions/stack.yaml`.
- When these probe-contract and documentation fixes merge to `main`, do the normal mainline release bookkeeping there instead of on this workstream branch.
- The unrelated live platform debt left visible by this replay is the stale `postgres-replica-lv3` production inventory entry and the `step-ca-proxy` certificate SAN still bound to legacy `100.118.189.95`.
