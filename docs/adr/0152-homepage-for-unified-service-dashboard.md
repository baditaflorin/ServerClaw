# ADR 0152: Homepage for Unified Service Dashboard

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform now has over 20 deployed services across 7 VMs, plus new services added in ADRs 0143–0151. An operator or agent starting a new session must know where each service lives, what its URL is, what Keycloak realm it uses, and whether it is currently healthy — before they can do any productive work.

This information exists in:
- `versions/stack.yaml` — the canonical service inventory.
- `config/service-capability-catalog.json` (ADR 0075) — service metadata including health probe URLs.
- `config/subdomain-catalog.json` (ADR 0076) — published subdomain URLs.
- The platform manifest (ADR 0132) — a machine-readable summary.
- The operator's mental model — accumulated over time, not documented anywhere.

There is no single **browser-accessible dashboard** that shows:
- All services, their URLs, and their current health status.
- Which VM each service runs on.
- Quick links to the most common operator actions (open Grafana, open Windmill, check the mutation ledger, trigger a convergence).
- Upcoming maintenance windows.
- The platform version and recent changes.

Without a unified dashboard, onboarding a new operator or recovering access after a long absence requires consulting multiple config files to find service URLs. This is especially impactful in break-glass scenarios where speed matters.

**Homepage** (by benphelps / gethomepage.dev) is a self-hosted, highly configurable service dashboard with:
- A clean web UI showing service tiles with names, URLs, icons, and live status.
- Integration with 100+ services for live status widgets (Proxmox, Grafana, Docker, Uptime Kuma, Gitea, etc.).
- A YAML-driven configuration that can be generated from the platform's service catalog.
- A REST API for programmatic configuration updates.
- No authentication of its own (auth is handled at the nginx layer).

## Decision

We will deploy **Homepage** on `docker-runtime-lv3` as the platform's unified service dashboard, auto-generated from the service capability catalog.

### Deployment

```yaml
# In versions/stack.yaml
- service: homepage
  vm: docker-runtime-lv3
  image: ghcr.io/gethomepage/homepage:latest
  port: 3090
  access: tailscale_only
  config_volume: /data/homepage
  subdomain: home.lv3.org
  auth: keycloak_oidc
```

### Configuration generation

Homepage's configuration files (`services.yaml`, `widgets.yaml`, `bookmarks.yaml`) are auto-generated from the platform's canonical sources by a Windmill workflow `generate-homepage-config` that runs on every platform version increment:

```python
# scripts/generate_homepage_config.py
# Reads: versions/stack.yaml, config/service-capability-catalog.json, config/subdomain-catalog.json
# Writes: /data/homepage/services.yaml, /data/homepage/widgets.yaml

def generate_services():
    services = []
    for svc in load_stack_services():
        catalog_entry = load_capability_catalog().get(svc.service_id)
        subdomain_entry = load_subdomain_catalog().get(svc.subdomain)
        if not subdomain_entry or subdomain_entry.access == "internal_only":
            continue  # Skip services without a routable URL
        services.append({
            "name": catalog_entry.display_name,
            "url": f"https://{subdomain_entry.fqdn}",
            "icon": catalog_entry.icon,
            "ping": catalog_entry.health_probe_url,
            "description": catalog_entry.description,
        })
    return services
```

This means Homepage configuration is never manually edited; it reflects the declared platform state. When a new service is added to `versions/stack.yaml` and the Windmill workflow runs, it automatically appears in the dashboard.

### Dashboard layout

```yaml
# Generated services.yaml structure

services:
  - Infrastructure:
      - Proxmox:    { url: "...", icon: "proxmox.png", widget: { type: proxmox, ... } }
      - Gitea:      { url: "https://git.lv3.org", icon: "gitea.png", widget: { type: gitea, ... } }

  - Operations:
      - Windmill:   { url: "...", icon: "windmill.png" }
      - Semaphore:  { url: "https://ansible.lv3.org", icon: "semaphore.png" }
      - n8n:        { url: "https://n8n.lv3.org", icon: "n8n.png" }
      - Ops Portal: { url: "https://ops.lv3.org", icon: "tools.png" }

  - Observability:
      - Grafana:     { url: "https://grafana.lv3.org", icon: "grafana.png", widget: { type: grafana, ... } }
      - Loki:        { url: "...", icon: "loki.png" }
      - Dozzle:      { url: "https://logs.lv3.org", icon: "docker.png" }
      - Langfuse:    { url: "https://langfuse.lv3.org", icon: "langfuse.png" }
      - GlitchTip:   { url: "...", icon: "glitchtip.png" }

  - Identity & Security:
      - Keycloak:    { url: "https://sso.lv3.org", icon: "keycloak.png" }
      - Vaultwarden: { url: "https://vault.lv3.org", icon: "bitwarden.png" }
      - OpenBao:     { url: "...", icon: "vault.png" }

  - AI & Search:
      - Open WebUI:  { url: "...", icon: "openwebui.png" }
      - Ollama:      { url: "...", icon: "ollama.png" }
      - SearXNG:     { url: "https://search.lv3.org", icon: "searxng.png" }

  - Data:
      - NetBox:     { url: "...", icon: "netbox.png" }
      - Postgres:   { url: "...", icon: "postgres.png" }
```

### Top-bar widgets

Homepage's top-bar widgets show the most operationally relevant platform state:

```yaml
# Generated widgets.yaml
widgets:
  - platformManifest:
      url: "http://platform-api/v1/manifest"
      # Shows: platform version, health summary, open incidents count

  - datetime:
      text_size: xl
      format:
        dateStyle: short
        timeStyle: short

  - search:
      provider: custom
      url: "https://search.lv3.org/search?q="   # SearXNG integration
      target: _blank
```

### Agent use of the Homepage API

The Homepage configuration API is used by the self-describing platform manifest generator (ADR 0132) to check service URL reachability and update tile status from the health composite index (ADR 0128):

```python
# After platform manifest refresh, update Homepage widget data
for service_id, health in manifest.health.services.items():
    homepage.update_widget_status(
        service_id=service_id,
        status=health["composite_status"],
        score=health["composite_score"],
    )
```

### Break-glass value

In a break-glass scenario where an operator has lost access to the platform, `https://home.lv3.org` (accessible via Tailscale/Headscale after device re-enrollment) is the single URL that gives the operator a complete picture of all services and their current health. The dashboard is the "where do I start?" answer for any platform access scenario.

## Consequences

**Positive**

- New operators have a single URL that shows all platform services, their health status, and quick access links. Onboarding time for a new operator is reduced from "read several YAML files" to "open a browser".
- The auto-generated configuration ensures the dashboard is always accurate; services cannot be forgotten on the dashboard when they are added or removed from the stack.
- The SearXNG integration in the search widget gives operators a private web search from the dashboard, without opening a separate browser tab.

**Negative / Trade-offs**

- Homepage is another service to operate and back up. It is very lightweight (static web app served by a Node.js server) but adds to the service count.
- The auto-generation workflow must be triggered after every service addition. If an operator adds a service without running the Windmill workflow, the dashboard will be out of sync until the next platform version increment triggers it.
- Homepage's live status widgets (Proxmox health, Grafana dashboards counts, Docker container counts) require API keys for each integration. These are additional credentials to manage in OpenBao, adding setup overhead for each service.

## Boundaries

- Homepage is a read-only dashboard. No platform operations are triggered from the Homepage UI itself; all actions go through the ops portal (ADR 0093), platform CLI, or Windmill.
- Homepage configuration is always auto-generated; manual edits to the generated files will be overwritten on the next `generate-homepage-config` run.

## Related ADRs

- ADR 0048: Command catalog (quick-action bookmarks on the dashboard)
- ADR 0056: Keycloak SSO (Homepage OIDC login)
- ADR 0075: Service capability catalog (source for dashboard service entries)
- ADR 0076: Subdomain governance (source for service URLs)
- ADR 0093: Interactive ops portal (primary action surface; Homepage links to it)
- ADR 0128: Platform health composite index (health status shown per tile)
- ADR 0132: Self-describing platform manifest (updates Homepage widget data)
- ADR 0144: Headscale (operator accesses home.lv3.org via mesh VPN)
- ADR 0148: SearXNG (integrated in Homepage search widget)
