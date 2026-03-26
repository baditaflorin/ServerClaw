# Workstream ADR 0148: SearXNG for Agent Web Search

- ADR: [ADR 0148](../adr/0148-searxng-for-agent-web-search.md)
- Title: Private SearXNG runtime for agent and operator web search on docker-runtime-lv3
- Status: live_applied
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: 2026-03-25
- Branch: `codex/adr-0148-searxng-web-search`
- Worktree: `.worktrees/adr-0148-searxng-web-search`
- Owner: codex
- Depends On: `adr-0023-docker-runtime`, `adr-0044-windmill`, `adr-0060-open-webui`, `adr-0068-container-image-policy`
- Conflicts With: none
- Shared Surfaces: `docker-runtime-lv3`, `collections/ansible_collections/lv3/platform/roles/searxng_runtime`, `roles/open_webui_runtime`, `roles/proxmox_tailscale_proxy`, `platform/web/`, `config/image-catalog.json`, `config/subdomain-catalog.json`

## Scope

- add a repo-managed SearXNG runtime role and playbook
- pin and scan the SearXNG and Valkey images
- publish the operator entrypoint on the Proxmox host Tailscale IP and at `search.lv3.org`
- wire Open WebUI to use the local SearXNG JSON endpoint
- add a small repo-side web search client for controlled consumers such as incident triage
- document the rollout and verification path

## Non-Goals

- public edge publication of the SearXNG UI
- full-page scraping or content summarisation of web search results
- replacing the internal ADR and runbook search fabric from ADR 0121

## Expected Repo Surfaces

- `playbooks/searxng.yml`
- `collections/ansible_collections/lv3/platform/playbooks/searxng.yml`
- `collections/ansible_collections/lv3/platform/roles/searxng_runtime/`
- `platform/web/search.py`
- `docs/runbooks/configure-searxng.md`
- `docs/adr/0148-searxng-for-agent-web-search.md`
- `docs/workstreams/adr-0148-searxng-web-search.md`
- `config/image-catalog.json`
- `config/service-capability-catalog.json`
- `config/health-probe-catalog.json`
- `config/subdomain-catalog.json`
- `config/controller-local-secrets.json`
- `config/secret-catalog.json`
- `inventory/host_vars/proxmox_florin.yml`
- `inventory/group_vars/platform.yml`
- `workstreams.yaml`

## Expected Live Surfaces

- SearXNG responds on `http://10.10.10.20:8881`
- the Proxmox host Tailscale IP serves SearXNG on `http://100.64.0.1`
- `search.lv3.org` resolves to the Proxmox host Tailscale IP for tailnet users
- Open WebUI renders `ENABLE_WEB_SEARCH=True` with `WEB_SEARCH_ENGINE=searxng`
- triage reports can attach bounded `web_search_references` when no rule matches

## Verification

- Run `uv run --with pytest --with pyyaml python -m pytest tests/test_searxng_runtime_role.py tests/test_web_search_client.py tests/test_incident_triage.py -q`
- Run `ANSIBLE_CONFIG=ansible.cfg ANSIBLE_COLLECTIONS_PATH=collections uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/searxng.yml --syntax-check`
- Run `python3 scripts/generate_platform_vars.py --check`
- Run `python3 scripts/uptime_contract.py --check`

## Merge Criteria

- the SearXNG runtime is fully repo-managed and pinned to scanned images
- Open WebUI is re-rendered to use the local SearXNG endpoint
- the tailnet hostname resolves correctly after the live apply
- ADR 0148 and this workstream record the final repo and platform implementation versions

## Notes For The Next Assistant

- keep the operator surface tailnet-only; do not route SearXNG through the public edge in this workstream
- the live host's current Tailscale IPv4 is `100.64.0.1`; the older `100.118.189.95` value was stale repo state discovered during this workstream
- management access was restored on 2026-03-26. Verified from the controller:
  `100.64.0.1:22`, `100.64.0.1:2222`, and `100.64.0.1:8006` are open again.
- the guest runtime and host proxy are now live. Verified from the controller:
  `http://10.10.10.20:8881/search?q=proxmox%20ve&format=json` returned `200`
  with results, and `http://100.64.0.1/search?q=proxmox%20ve&format=json`
  returned `200` with results on 2026-03-26.
- SearXNG needed an additional managed `limiter.toml` plus a one-time forced
  container recreate on 2026-03-26 because the first live rollout had already
  written the config files without restarting the container. Keep that history
  in mind if you debug another stale-runtime mismatch.
- the final DNS publication completed on 2026-03-26 after the controller shell
  was rerun with `HETZNER_DNS_API_TOKEN`. Verified from the controller:
  `dig +short @1.1.1.1 search.lv3.org` returned `100.64.0.1`, and
  `http://search.lv3.org/search?q=proxmox%20ve&format=json` returned `200`
  with results.
- the first DNS publication attempt failed at `12:53 UTC` on 2026-03-26
  because Hetzner's legacy DNS write API was in a scheduled brownout window and
  returned `503`. The successful localhost-only retry started at `13:01 UTC`.
