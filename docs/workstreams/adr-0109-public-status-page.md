# Workstream ADR 0109: Public Status Page

- ADR: [ADR 0109](../adr/0109-public-status-page.md)
- Title: Uptime Kuma status page at status.lv3.org with maintenance window integration plus Uptime Robot external monitoring for last-resort independence
- Status: ready
- Branch: `codex/adr-0109-public-status-page`
- Worktree: `../proxmox_florin_server-public-status-page`
- Owner: codex
- Depends On: `adr-0015-dns-subdomains`, `adr-0021-nginx-edge`, `adr-0027-uptime-kuma`, `adr-0076-subdomain-governance`, `adr-0080-maintenance-window`, `adr-0096-slo-tracking`, `adr-0097-alerting-routing`
- Conflicts With: none
- Shared Surfaces: `scripts/maintenance_window_tool.py`, nginx edge config, `config/subdomain-catalog.json`, Uptime Kuma service

## Scope

- configure Uptime Kuma status page via Uptime Kuma API or Ansible role: create public status page `lv3-platform` with correct monitors
- write `scripts/configure_uptime_kuma_status_page.py` — idempotent script that creates/updates the Uptime Kuma status page configuration
- add nginx vhost `status.lv3.org` — proxy to `uptime-kuma:3001` without OIDC auth; port 443 with Let's Encrypt cert
- add `status.lv3.org` to `config/subdomain-catalog.json` as a public subdomain
- update `scripts/maintenance_window_tool.py` — add `post_status_page_maintenance()` call when a window is declared; uses Uptime Kuma API to create a maintenance announcement
- configure Uptime Robot external monitors (via Uptime Robot API) — 3 monitors for the most critical external-facing services
- store Uptime Robot API key in OpenBao at `platform/uptime-robot/api-key`
- add Let's Encrypt DNS-01 certificate for `status.lv3.org` on nginx-lv3
- add SLO entry for the status page itself to `config/slo-catalog.json`
- add health probe for the status page to `config/health-probe-catalog.json`
- add Uptime Robot Mattermost webhook configuration for external alert routing

## Non-Goals

- Custom status page design beyond Uptime Kuma's built-in themes
- Incident postmortem publication on the status page (manual process)
- Status page with per-component uptime history graphs (Uptime Kuma's built-in history is sufficient)

## Expected Repo Surfaces

- `scripts/configure_uptime_kuma_status_page.py`
- `scripts/maintenance_window_tool.py` (patched: status page maintenance announcement)
- `config/subdomain-catalog.json` (patched: `status.lv3.org` added)
- `config/slo-catalog.json` (patched: status page SLO added)
- `config/health-probe-catalog.json` (patched: status page probe added)
- nginx vhost config for `status.lv3.org` (in `roles/nginx_edge_publication/` templates)
- `docs/adr/0109-public-status-page.md`
- `docs/workstreams/adr-0109-public-status-page.md`

## Expected Live Surfaces

- `https://status.lv3.org` is publicly accessible (no login required)
- Status page shows all 6 configured monitors with current status
- Declaring a maintenance window via `lv3 maintenance start` creates a maintenance announcement on the status page
- Uptime Robot dashboard shows 3 monitors for `sso.lv3.org`, `grafana.lv3.org`, and `status.lv3.org`
- Uptime Robot Mattermost webhook is configured and posts to `#platform-ops` on status changes

## Verification

- Open `https://status.lv3.org` in a browser (unauthenticated) → status page renders with all monitors green
- `lv3 maintenance start --service keycloak --duration 30m` → verify status page shows "Under Maintenance" for the SSO monitor within 60 seconds
- Check Uptime Robot account: 3 monitors created and reporting UP for all three services
- Stop Keycloak temporarily; verify Uptime Robot sends alert to Mattermost `#platform-ops` within 10 minutes; restart Keycloak; verify resolution notification

## Merge Criteria

- `https://status.lv3.org` accessible publicly without authentication
- All 6 service monitors configured in the Uptime Kuma status page
- Maintenance window integration tested
- Uptime Robot monitors configured and active
- SLO and health probe added for the status page itself

## Notes For The Next Assistant

- Uptime Kuma's API is documented at `https://github.com/louislam/uptime-kuma/wiki/API`; it uses Socket.IO rather than REST; the `uptime-kuma-api` Python package wraps this for scripting use
- The status page must use the `slug: lv3-platform` to ensure the URL is `https://uptime-kuma:3001/status/lv3-platform`; the nginx proxy must pass this path correctly
- Let's Encrypt cert for `status.lv3.org`: add to the certbot renewal config on `nginx-lv3`; the DNS-01 challenge is already configured (ADR 0021); add `status.lv3.org` to the domain list in the certbot command
- Uptime Robot webhook format for Mattermost: Uptime Robot sends a POST with a specific JSON payload; a small webhook adapter script on the Mattermost incoming webhook endpoint may be needed to translate the format; alternatively, use Uptime Robot's built-in Mattermost integration if available in the configured plan
