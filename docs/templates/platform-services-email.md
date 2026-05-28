# Platform Services Email Template

Send this after onboarding to give the operator a live-tested list of
deployed and functional services. Only includes services confirmed
reachable with working SSO flows (tested {{DATE}}).

Re-run `scripts/check_service_health.sh` before sending to refresh the list.

---

## Subject Line

```
[0mcp.com] Your platform services — deployed and live
```

## Body (plain text)

```
Hi <FIRST_NAME>,

Here are the services currently deployed and functional on 0mcp.com.
All SSO-protected services use the same login at https://sso.0mcp.com/realms/0mpc/account/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SSO & IDENTITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  https://sso.0mcp.com/realms/0mpc/account/   Keycloak — login & password change
  https://vault.0mcp.com                      Vaultwarden — password manager

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 OBSERVABILITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  https://grafana.0mcp.com                    Grafana — metrics & dashboards
  https://uptime.0mcp.com                     Uptime Kuma — service uptime
  https://status.0mcp.com                     Status page
  https://errors.0mcp.com                     GlitchTip — error tracking
  https://logs.0mcp.com                       Dozzle — container logs
  https://analytics.0mcp.com                  Plausible — web analytics
  https://langfuse.0mcp.com                   Langfuse — LLM observability

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 DEVELOPMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  https://git.0mcp.com                        Gitea — git hosting
  https://ci.0mcp.com                         Woodpecker CI — pipelines
  https://registry.0mcp.com                   Harbor — container registry
  https://build.0mcp.com                      Docker build server

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 AI & AGENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  https://agents.0mcp.com                     Dify — AI agent builder
  https://search.0mcp.com                     SearXNG — private search

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PRODUCTIVITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  https://wiki.0mcp.com                       Outline — docs & wiki
  https://tasks.0mcp.com                      Plane — project management
  https://draw.0mcp.com                       Excalidraw — diagrams
  https://n8n.0mcp.com                        n8n — workflow automation
  https://home.0mcp.com                       Homepage — platform dashboard
  https://ntfy.0mcp.com                       ntfy — push notifications

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PLATFORM INFRASTRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  https://coolify.0mcp.com                    Coolify — app deployment
  https://apps.0mcp.com                       Coolify apps (redirects to Coolify)
  https://ops.0mcp.com                        Ops portal
  https://api.0mcp.com                        API gateway
  https://proxmox.0mcp.com                    Proxmox — hypervisor UI
  https://mail.0mcp.com                       Stalwart — mail server
  https://flags.0mcp.com                      Flagsmith — feature flags
  https://billing.0mcp.com                    Lago — usage billing
  https://annotate.0mcp.com                   Label Studio — ML annotation
  https://browser.0mcp.com                    Neko — remote browser
  https://ca.0mcp.com                         step-ca — SSH certificate authority

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 VPN (required for internal services)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  https://headscale.0mcp.com                  Headscale — VPN coordination

  sudo tailscale up \
    --login-server https://headscale.0mcp.com \
    --authkey <HEADSCALE_AUTHKEY> \
    --hostname <USERNAME>-laptop

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 NOT YET DEPLOYED (502 / coming soon)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  chat.0mcp.com      Open WebUI
  cloud.0mcp.com     Nextcloud
  paperless.0mcp.com Paperless
  bi.0mcp.com        Apache Superset
  data.0mcp.com      Directus
  matrix.0mcp.com    Matrix Synapse
  grist.0mcp.com     Grist
  minio.0mcp.com     MinIO (requires auth)

Welcome,
0mcp.com platform
```

## Placeholders Reference

| Placeholder | Source |
|-------------|--------|
| `<FIRST_NAME>` | From request |
| `<HEADSCALE_AUTHKEY>` | `headscale preauthkeys create --user 1 --expiration 720h -o json` on proxmox |

## Service Status Last Verified

- Tested: 2026-05-27
- SSO realm: `0mpc` (not `lv3`)
- Grafana auth_url fixed to `realms/0mpc`
- All SSO redirects confirmed pointing to `realms/0mpc`
