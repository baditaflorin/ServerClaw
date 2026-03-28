# Workstream ws-0021-edge-cert-repair: Shared Edge Certificate Expansion Repair

- ADR: [ADR 0021](../adr/0021-public-subdomain-publication-at-the-nginx-edge.md)
- Title: repair shared edge certificate expansion during service-specific converges
- Status: live_applied
- Branch: `codex/wiki-edge-cert-fix`
- Worktree: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/wiki-edge-cert-fix`
- Owner: codex
- Included In Repo Version: `0.177.28`
- Depends On: `adr-0021-public-subdomain-publication`, `adr-0033-declarative-service-topology-catalog`, `adr-0101-automated-certificate-lifecycle-management`, `adr-0199-outline-living-knowledge-wiki`, `adr-0202-excalidraw-auto-generated-architecture-diagrams`
- Conflicts With: none
- Shared Surfaces: `playbooks/{outline,excalidraw,public-edge,langfuse,homepage,keycloak,headscale,n8n,uptime-kuma}.yml`, `collections/ansible_collections/lv3/platform/playbooks/{dozzle,headscale,keycloak,n8n,public-edge,uptime-kuma}.yml`, `tests/test_edge_publication_playbooks.py`, `receipts/live-applies/`, `workstreams.yaml`

## Scope

- keep shared-edge publication playbooks aligned with the canonical platform topology during service-specific converges
- prevent certificate SAN drift when a service replay republishes the shared edge from a clean worktree
- restore the live publication for `wiki.lv3.org` and preserve `draw.lv3.org` in the same certificate and rendered edge config

## Verification

- `uv run --with pytest python -m pytest -q tests/test_edge_publication_playbooks.py tests/test_outline_playbook.py tests/test_n8n_playbook.py tests/test_dozzle_playbook.py`
- `ANSIBLE_HOST_KEY_CHECKING=False uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/outline.yml --syntax-check -e env=production`
- `ANSIBLE_HOST_KEY_CHECKING=False uvx --from ansible-core ansible-playbook -i inventory/hosts.yml playbooks/excalidraw.yml --syntax-check -e env=production`
- `make generate-changelog-portal docs`
- `HETZNER_DNS_API_TOKEN=... make configure-edge-publication env=production`
- `curl -I https://wiki.lv3.org`
- `curl -I https://wiki.lv3.org/_health`
- `openssl s_client -connect wiki.lv3.org:443 -servername wiki.lv3.org`
- `grep -n 'wiki\.lv3\.org\|draw\.lv3\.org' /etc/nginx/sites-available/lv3-edge.conf`
- `python3 scripts/sync_docs_to_outline.py verify --repo-root /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/wiki-edge-cert-fix --base-url https://wiki.lv3.org --api-token-file /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/outline/api-token.txt`

## Outcome

- the hotfix root cause was branch-local service replays invoking `lv3.platform.nginx_edge_publication` without loading `inventory/group_vars/platform.yml`, so the rendered shared-edge config and SAN expansion set could silently drop repo-managed hostnames
- every service playbook that republishes the shared edge now loads the canonical platform vars explicitly, and a regression test guards that contract
- the live repair replay restored `wiki.lv3.org` and `draw.lv3.org` to `/etc/nginx/sites-available/lv3-edge.conf`, expanded the shared certificate SANs to include both hostnames again, and returned `HTTP/2 200` for `https://wiki.lv3.org` and `https://wiki.lv3.org/_health`
- `python3 scripts/sync_docs_to_outline.py verify ...` returned `outline living collections verified` after the repair, confirming the published Outline surface is healthy again
- the canonical mainline replay from merged `main` completed on `2026-03-28` and is recorded in `receipts/live-applies/2026-03-28-adr-0021-shared-edge-certificate-repair-mainline-live-apply.json`
- remaining for merge to `main`: none

## Merge Criteria

- branch push passes with the new edge-publication regression coverage
- the merged `main` replay of `make configure-edge-publication env=production` preserves the shared certificate SAN set for all repo-managed public hostnames
- `versions/stack.yaml`, `changelog.md`, `VERSION`, `README.md`, and release notes are updated only on the final integrated `main` step
