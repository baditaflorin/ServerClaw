# Workstream ws-0196-live-apply: Live Apply ADR 0196 From Latest `origin/main`

- ADR: [ADR 0196](../adr/0196-netdata-realtime-streaming-metrics.md)
- Title: production live apply for Netdata parent and child streaming metrics plus the authenticated `realtime.example.com` surface from the latest `origin/main`
- Status: merged
- Implemented In Repo Version: 0.177.25
- Live Applied In Platform Version: 0.130.32
- Implemented On: 2026-03-27
- Live Applied On: 2026-03-27
- Branch: `codex/ws-0196-main-merge-v2`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.worktrees/ws-0196-live-apply`
- Owner: codex
- Depends On: `adr-0011-monitoring`, `adr-0071-agent-observation-loop`, `adr-0133-portal-authentication-by-default`
- Conflicts With: none
- Shared Surfaces: `collections/ansible_collections/lv3/platform/roles/netdata_runtime/`, `collections/ansible_collections/lv3/platform/roles/monitoring_vm/`, `collections/ansible_collections/lv3/platform/roles/nginx_edge_publication/`, `config/service-capability-catalog.json`, `config/subdomain-catalog.json`, `receipts/live-applies/`

## Scope

- replay ADR 0196 from an isolated latest-main worktree and branch suitable for
  parallel agent work
- apply the Netdata parent and child topology live on production
- verify the repo automation, validation, Prometheus export, authenticated edge
  route, and observation-loop integration end to end
- leave protected integration files for merge-to-main instead of updating them
  on this workstream branch

## Verification

- `uv run --with pytest --with jsonschema python -m pytest tests/test_generate_platform_vars.py tests/test_subdomain_catalog.py tests/test_validate_service_catalog.py tests/test_nginx_edge_publication_role.py tests/test_monitoring_vm_role.py tests/test_netdata_runtime_role.py tests/test_realtime_playbook.py -q`
- `uv run --with pyyaml --with jsonschema python scripts/validate_repository_data_models.py --validate`
- `make syntax-check-realtime`
- `make workflow-info WORKFLOW=converge-realtime`
- `./scripts/validate_repo.sh health-probes alert-rules agent-standards`
- `BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 make live-apply-service service=realtime env=production EXTRA_ARGS='-e bypass_promotion=true'`
- `HETZNER_DNS_API_TOKEN=... BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 make converge-realtime env=production`
- `make uptime-kuma-manage ACTION=bootstrap UPTIME_KUMA_ARGS='--base-url https://uptime.example.com'`
- `make uptime-kuma-manage ACTION=ensure-monitors`
- `HETZNER_DNS_API_TOKEN=... make provision-subdomain FQDN=realtime.example.com env=production`
- `dig +short realtime.example.com`
- `curl -skI https://realtime.example.com/`

## Outcome

- the production Netdata parent-plus-children topology is live on
  `monitoring`, `proxmox-host`, `nginx-edge`, `docker-runtime`, and
  `postgres`
- the shared authenticated edge now publishes `https://realtime.example.com` with
  the expanded Let's Encrypt certificate and the expected oauth2 sign-in
  redirect
- the final Prometheus query for `netdata_info{job="netdata"}` returned five
  realtime series, confirming ingestion of the consolidated parent export
- the generated Uptime Kuma contract now includes `Realtime Metrics Private`,
  and monitor management works from a separate worktree through the shared auth
  file path
- the full live-apply evidence is recorded in
  `receipts/live-applies/2026-03-27-adr-0196-netdata-realtime-streaming-metrics-live-apply.json`
- the dedicated `converge-realtime` workflow wrapper is now catalogued,
  validated, and proven against production in addition to the generic
  `live-apply-service` path
- the latest-main merge replay exposed missing `platform.yml` inheritance inside
  the realtime playbook; adding explicit `vars_files` loading and rerunning
  `make converge-realtime env=production` restored the live realtime edge vhost
  and reconfirmed the `302` oauth2 sign-in redirect at `https://realtime.example.com/`

## Mainline Integration

- merged to `main` in repository version `0.177.25`
- the protected integration files and realtime receipt mapping are now recorded
  on `main`
