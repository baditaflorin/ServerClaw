# Configure Homepage

## Purpose

This runbook converges the Homepage unified service dashboard defined by ADR 0152
and verifies both the private runtime and the authenticated public edge route.

## Result

- `docker-runtime-lv3` runs Homepage from `/opt/homepage`
- Homepage config is regenerated from the canonical service and subdomain catalogs on every converge
- `home.lv3.org` is published on the shared NGINX edge behind the repo-managed Keycloak oauth2-proxy gate
- Uptime Kuma manages the `Homepage Public` monitor for the new dashboard URL

## Commands

Syntax-check the Homepage workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-homepage
```

Converge the Homepage runtime and edge publication:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-homepage
```

Push the generated Uptime Kuma monitor set after the health-probe catalog changes:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make uptime-kuma-manage ACTION=ensure-monitors
```

## Verification

Verify the private Homepage listener on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.118.189.95 \
  ops@10.10.10.20 \
  'curl -fsS http://10.10.10.20:3090/'
```

Verify the public hostname is routed through the shared authenticated edge:

```bash
curl -Ik https://home.lv3.org
```

Verify the Uptime Kuma monitor exists:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make uptime-kuma-manage ACTION=list-monitors
```

## Operating Notes

- Homepage is intentionally read-only; use `ops.lv3.org`, the CLI, or service-native consoles for actions.
- Do not hand-edit the files under `/opt/homepage/config`; they are overwritten on the next converge.
- Keep `home.lv3.org` in the shared authenticated-edge set so the dashboard does not become a new anonymous surface.
