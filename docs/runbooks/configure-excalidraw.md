# Configure Excalidraw

## Purpose

This runbook converges the ADR 0202 Excalidraw runtime and regenerates the
committed architecture diagrams that are intended to be opened or imported from
the private `draw.example.com` surface.

## Result

- `docker-runtime` runs the Excalidraw frontend and the collaboration room from `/opt/excalidraw`
- `draw.example.com` is published through the shared NGINX edge behind the repo-managed oauth2-proxy gate
- the committed `.excalidraw` scene files under `docs/diagrams/` are generated from repo-managed platform data
- Uptime Kuma manages the `Excalidraw Public` monitor for the new publication

## Commands

Regenerate the committed architecture diagrams:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
uv run --with pyyaml --with jsonschema python scripts/generate_diagrams.py --write
```

Syntax-check the Excalidraw workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make syntax-check-excalidraw
```

Converge the Excalidraw runtime and edge publication:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
make converge-excalidraw
```

Refresh the repo-managed Uptime Kuma monitor set after health-probe changes:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
uv run --with pyyaml python scripts/uptime_contract.py --write
make uptime-kuma-manage ACTION=ensure-monitors
```

## Verification

Verify the private Excalidraw frontend listener on `docker-runtime`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:3095/ >/dev/null'
```

Verify the private collaboration room listener returns the upstream health banner:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:3096/'
```

Verify public DNS is present for `draw.example.com`:

```bash
dig +short draw.example.com @8.8.8.8
```

Verify the public hostname is routed through the shared authenticated edge:

```bash
curl -Ik --resolve draw.example.com:443:203.0.113.1 https://draw.example.com
```

Verify the committed diagram set is current:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
uv run --with pyyaml --with jsonschema python scripts/generate_diagrams.py --check
```

## Operating Notes

- The stock Excalidraw frontend image does not self-configure a private collaboration origin, so the runtime bootstraps a deterministic asset patch on each container start.
- Keep `draw.example.com` inside the shared authenticated-edge set so the architecture diagrams stay private to operators.
- Treat the files under `docs/diagrams/` as generated artifacts. Regenerate them instead of hand-editing them.
- Right after a fresh DNS create, some recursive resolvers may lag. Use `dig @8.8.8.8` plus `curl --resolve` for immediate verification, then fall back to plain `curl` once public recursion catches up.
