# Refresh Discovery Surfaces

## Overview

Refresh all operator-facing discovery surfaces (home.example.com, ops.example.com, wiki.example.com) to sync with the current service catalog and ADR corpus. This is the cascade entry point after service deployments or when you need to push documentation and service listing changes to the portals.

## Symptoms of Stale Surfaces

- New services deployed but not appearing on home.example.com or ops.example.com
- ADRs committed to git but not visible on wiki.example.com
- Service metadata changes (URLs, lifecycle status, ADR references) not propagated to discovery portals

## Prerequisites

- Bootstrap SSH key at `.local/ssh/bootstrap.id_ed25519` (for Proxmox SSH access)
- Outline API token at `.local/outline/api-token.txt` (for wiki sync; see refresh-outline-api-token.md if expired)
- Read access to the service catalog (config/service-capability-catalog.json)
- Read access to the ADR corpus (docs/adr/*.md)

## Quick Start

### Full Refresh (All Surfaces)

```bash
make refresh-discovery-surfaces env=production
```

This runs the complete cascade:
1. Regenerate platform-manifest.json and discovery artifacts
2. Sync ADRs and docs to wiki.example.com (Outline)
3. Converge homepage (home.example.com on runtime-general)
4. Converge ops portal (ops.example.com on docker-runtime)
5. Refresh NGINX edge configs (nginx-edge)

Expected duration: ~3–5 minutes

### With Trigger Attribution (For Audit Trail)

```bash
make refresh-discovery-surfaces env=production trigger_service=neko
```

The `trigger_service` parameter documents which service deployment or change triggered the refresh. This is logged in playbook output for audit purposes.

### Selective Refresh (Skip Surfaces that Don't Need Updating)

Skip refreshing Outline (wiki.example.com) if no ADRs were added/modified:

```bash
make refresh-discovery-surfaces env=production refresh_outline=false
```

Available toggles:
- `refresh_homepage=false` — Skip refreshing home.example.com
- `refresh_ops_portal=false` — Skip refreshing ops.example.com
- `refresh_outline=false` — Skip syncing wiki.example.com (saves ~90 seconds if no docs changed)
- `refresh_platform_manifest=false` — Skip regenerating platform-manifest.json
- `refresh_discovery_artifacts=false` — Skip regenerating discovery artifacts

## Understanding the Cascade Phases

### Phase 1: Local Artifact Regeneration

Runs on the controller host (your machine or CI/CD runner).

- **platform_manifest.py** — Regenerates build/platform-manifest.json by merging the service catalog with generation scripts
- **generate_discovery_artifacts.py** — Regenerates build/onboarding/* artifacts (agent topology, service index, etc.)

These files are transient and regenerated on every refresh.

### Phase 2: Sync Docs to Outline

Runs on the controller, calls the Outline API.

- **sync_docs_to_outline.py sync** — Syncs ADRs, runbooks, and landing pages from git to wiki.example.com
- Requires `.local/outline/api-token.txt` (OIDC token)
- If token is expired: See **Outline Token Expired?** section below

### Phase 3 & 4: Converge Remote Services

Runs on remote VMs (via Proxmox SSH).

- **homepage convergence** (runtime-general) — Pulls latest service catalog, regenerates home.example.com UI
- **ops portal convergence** (docker-runtime) — Pulls latest service catalog, regenerates ops.example.com UI

### Phase 5: Publish NGINX Edge Configs

Runs on NGINX edge (nginx-edge).

- Reloads NGINX configs for the updated discovery services
- Non-disruptive reload (existing connections preserved)

## Troubleshooting

### Outline Token Expired?

If sync_docs_to_outline.py returns HTTP 401:

```bash
python3 scripts/sync_docs_to_outline.py bootstrap-token
```

This re-authenticates with Keycloak and creates a fresh API token. Requires:
- `.local/keycloak/outline.automation-password.txt` (service account password)
- Keycloak running and reachable at `https://auth.example.com`

Then retry the full cascade:

```bash
make refresh-discovery-surfaces env=production
```

### Homepage or Ops Portal Convergence Fails

Both services depend on the current service-capability-catalog.json and dynamically generated configs. If convergence fails:

1. **Check service catalog syntax:**
   ```bash
   python3 -m json.tool config/service-capability-catalog.json > /dev/null && echo "Valid"
   ```

2. **Verify SSH access to the VM:**
   ```bash
   ssh -i .local/ssh/bootstrap.id_ed25519 ops@10.10.10.91 'uname -a'  # for runtime-general
   ```

3. **Check NGINX edge connectivity:**
   ```bash
   curl -I https://home.example.com
   curl -I https://ops.example.com
   ```

### Wiki (Outline) Sync Fails with Different Error

Check Outline availability and API token validity:

```bash
curl -H "Authorization: Bearer $(cat .local/outline/api-token.txt)" \
  https://wiki.example.com/api/collections.list
```

If 401, re-bootstrap the token (see above). If 5xx, Outline may be down or restarting.

## Related Procedures

- **refresh-outline-api-token.md** — Manual refresh of Outline OIDC token (if bootstrap-token fails)
- **configure-homepage.md** — Setup and troubleshooting for home.example.com
- **configure-ops-portal.md** — Setup and troubleshooting for ops.example.com
- **configure-outline.md** — Setup and troubleshooting for wiki.example.com

## Related ADRs

- **ADR 0383: Discovery Surface Refresh Cascade** — Architecture, evolution path, and constraints
- **ADR 0152: Homepage Service Dashboard** — Home page design and data flow
- **ADR 0093: Interactive Ops Portal** — Ops portal design and data flow
- **ADR 0199: Outline Living Knowledge Wiki** — Wiki design and sync strategy
- **ADR 0073: LV3 Platform Architecture** — Overall system topology
