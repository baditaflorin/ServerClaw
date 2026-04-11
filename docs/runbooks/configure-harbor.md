# Configure Harbor

## Purpose

This runbook converges the Harbor registry from ADR 0201 and validates the live `registry.example.com` cutover.

It covers:

- Harbor runtime deployment on `runtime-control`
- shared edge publication for `https://registry.example.com`
- repo-managed Keycloak OIDC bootstrap for Harbor operators
- repo-managed `check-runner` Harbor project bootstrap
- project robot credentials mirrored under `.local/harbor/`
- migration and validation of the existing check-runner images through Harbor

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `runtime-control`, `docker-build`, and `nginx-edge` are reachable through the Proxmox jump path
3. Keycloak is already live on `runtime-control`
4. `HETZNER_DNS_API_TOKEN` is available in the shell that runs the converge

## Entrypoints

- syntax check: `make syntax-check-harbor`
- preflight: `make preflight WORKFLOW=converge-harbor`
- converge: `HETZNER_DNS_API_TOKEN=... make converge-harbor`
- DNS publication if the record is still absent: `HETZNER_DNS_API_TOKEN=... make provision-subdomain FQDN=registry.example.com`

## Delivered Surfaces

The workflow manages these live surfaces:

- Harbor runtime under `/opt/harbor` on `runtime-control`
- Harbor data under `/opt/harbor/data`
- Harbor logs under `/var/log/harbor`
- shared public hostname `https://registry.example.com`
- Keycloak confidential client `harbor`
- Keycloak group `harbor-admins`
- Harbor project `check-runner`
- Harbor project robot account for `check-runner` image publication

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/harbor/admin-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/harbor/database-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/harbor/check-runner-robot.json`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/keycloak/harbor-client-secret.txt`

Treat the `.local/harbor/` subtree and the Harbor Keycloak client secret as recovery material and keep them out of git.

## Verification

Run these checks after converge:

1. `make syntax-check-harbor`
2. `curl -fsS https://registry.example.com/api/v2.0/ping`
3. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' ops@10.10.10.92 'docker compose -f /opt/harbor/installer/harbor/docker-compose.yml ps'`
4. `curl -fsS -u "admin:$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/harbor/admin-password.txt)" https://registry.example.com/api/v2.0/projects/check-runner`
5. `jq -r '.username + \":\" + .secret' /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/harbor/check-runner-robot.json`
6. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' ops@10.10.10.30 'docker pull registry.example.com/check-runner/python:3.12.10 && docker image inspect registry.example.com/check-runner/python:3.12.10 --format '"'"'{{index .RepoDigests 0}}'"'"''`

## Troubleshooting

- If `make converge-harbor` exits cleanly but `https://registry.example.com/api/v2.0/ping` still returns `502 Bad Gateway`, `http://127.0.0.1:8095/api/v2.0/ping` is connection refused on `runtime-control`, or `docker pull registry.example.com/check-runner/...` fails on `docker-build` with `received unexpected HTTP status: 502 Bad Gateway`, replay `make converge-docker-publication-assurance env=production` from the same checkout and rerun the full verification list above.
- This failure mode indicates stale Docker publication drift on the Harbor edge path: the Harbor containers may still appear present, but the published registry port binding or compose network membership can be incomplete until the publication-assurance replay re-establishes the canonical bridge and port-forward state.

## Notes

- Harbor currently uses the local filesystem backend. Migrating Harbor blob storage to the object-storage design from ADR 0203 remains a later mainline step.
- The `check-runner` Harbor project is intentionally public for pull compatibility during the initial migration, while push remains scoped to the generated project robot credential.
- Human operator browser sign-in is delegated to Keycloak OIDC; API bootstrap continues to use the Harbor `admin` credential mirrored under `.local/harbor/`.
