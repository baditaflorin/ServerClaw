# ADR 0151: n8n for Webhook and API Integration Automation

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

Windmill (ADR 0044) is the platform's primary workflow automation engine. It is well-suited for infrastructure workflows: running Ansible playbooks, triggering Windmill jobs from platform events, and driving multi-step intent execution. Windmill workflows are written in Python/TypeScript, are version-controlled, and integrate tightly with the platform's goal compiler and ledger.

However, Windmill is not well-suited for a different class of automation: **webhook and API integration glue**:

- Receiving a webhook from an external service (Hetzner billing alerts, uptime monitoring callbacks, GitHub repository notifications) and routing it to the appropriate platform action.
- Enriching an alert with data from multiple APIs before posting it to Mattermost (e.g., combining a Proxmox backup failure with the affected VM's NetBox metadata before posting to `#platform-alerts`).
- Sending a daily digest of platform events to a specific channel with a formatted summary.
- Bridging between protocols: receiving an HTTPS webhook and publishing to NATS, or reading from a REST API and writing to Postgres.
- Visual workflow building for operators who want to add a new integration without writing Python code.

Windmill can do all of these but requires Python code for each node. The visual workflow editor in Windmill is designed for script composition, not drag-and-drop API integration. For the integration glue category, a visual low-code automation tool is significantly more efficient.

**n8n** is a self-hosted, open-source workflow automation tool with 400+ built-in integrations, a visual node editor, webhook triggers, credential management, and an execution history. It is the self-hosted equivalent of Zapier or Make, but with full data sovereignty and a programmable API.

n8n and Windmill are complementary: Windmill owns infrastructure automation (Ansible, Docker, platform-specific workflows); n8n owns API integration automation (webhook routing, external service connectors, notification formatting).

## Decision

We will deploy **n8n** on `docker-runtime-lv3` as the platform's integration automation tool for non-infrastructure webhook and API workflows.

### Deployment

```yaml
# In versions/stack.yaml
- service: n8n
  vm: docker-runtime-lv3
  image: n8nio/n8n:latest
  port: 5678
  access: tailscale_only
  database: postgres-lv3
  subdomain: n8n.lv3.org
  keycloak_oidc: true
```

### Credential management

n8n's built-in credential store is used for third-party API keys (Hetzner API key, DNS provider API key, external monitoring webhooks). These are the same credentials that Vaultwarden (ADR 0147) manages for human use; n8n gets its own credential entries sourced from Vaultwarden's CLI at setup time.

### Canonical use cases

**Use case 1: Hetzner billing alert routing**

Hetzner sends billing alerts via email. An n8n workflow polls the Hetzner API monthly for cost data, compares against the previous month, and posts a formatted cost summary to Mattermost `#platform-ops`:

```
📊 Hetzner monthly cost: €8.50 (+0.3% vs last month)
  Server (CX52): €6.90 | Snapshots: €0.80 | Traffic: €0.80
```

**Use case 2: External webhook to NATS bridge**

Uptime Kuma (ADR 0027) sends a webhook when a monitor changes state. An n8n workflow receives the webhook and publishes a `platform.health.degraded` or `platform.health.recovered` NATS event (ADR 0124), integrating external monitoring with the platform's event taxonomy:

```json
// n8n node: "Publish to NATS"
{
  "topic": "platform.health.{{ $json.status === 'down' ? 'degraded' : 'recovered' }}",
  "payload": {
    "service_id": "{{ $json.monitorName }}",
    "source": "uptime_kuma",
    "ts": "{{ $now }}"
  }
}
```

**Use case 3: Daily platform digest**

A scheduled n8n workflow runs daily at 08:00 and assembles a digest by calling:
- The platform manifest API (ADR 0132) for overall health summary.
- The mutation ledger API for yesterday's executed workflows.
- The GlitchTip API for open incidents.

It posts the formatted digest to Mattermost `#platform-daily`.

**Use case 4: DNS zone change notification**

An n8n workflow polls the Hetzner DNS API every 15 minutes and compares the zone to the previous snapshot. On any change, it publishes a `platform.security.exposure_audit_alert` NATS event and posts to `#platform-security`.

### n8n API for agents

n8n exposes a REST API for triggering workflows programmatically. Platform agents can trigger n8n integration workflows when needed:

```python
# Trigger the "notify-external" n8n workflow from a Windmill job
n8n = N8nClient(base_url="http://n8n:5678", api_key=openbao.get("n8n/api-key"))
n8n.execute_workflow(
    workflow_id="hetzner-cost-report",
    payload={"period": "2026-03"},
)
```

### Boundaries with Windmill

| Use case | Tool |
|---|---|
| Run Ansible playbook | Windmill |
| Trigger platform intent (goal compiler) | Windmill (via platform CLI) |
| Route external webhook to NATS | n8n |
| Format and post notification to Mattermost | n8n (for complex formatting) or Windmill (for platform events) |
| Poll external API and compare to previous state | n8n |
| Multi-step infrastructure change with budget enforcement | Windmill |
| Send daily digest | n8n |

## Consequences

**Positive**

- External webhook handling (Hetzner, Uptime Kuma, DNS providers) is now integrated into the platform's event taxonomy via NATS, giving the triage engine and observation loop visibility into external events.
- The visual n8n editor makes it practical for an operator to add a new webhook integration in 10 minutes without writing Python code.
- n8n's execution history provides an audit trail for all integration automations, comparable to Windmill's job log for infrastructure workflows.

**Negative / Trade-offs**

- n8n is another service with its own credential store, update cycle, and backup requirements. The boundary between n8n and Windmill must be clearly understood by operators; otherwise, automation sprawls across both tools with no clear ownership.
- n8n workflows built via the visual editor are not version-controlled in the same way as Windmill scripts in the platform repo. n8n has a workflow export format (JSON), but it is less readable in a code review than a Python script. Operators must export and commit n8n workflow exports to the repo periodically.

## Boundaries

- n8n handles integration and webhook glue. Infrastructure automation (Ansible, Docker, platform services) stays in Windmill.
- n8n workflows that trigger platform actions (e.g., an incoming webhook that triggers a platform deployment) must do so by publishing to NATS or calling the Windmill API; they must not call Ansible or Docker directly.

## Related ADRs

- ADR 0044: Windmill (primary infrastructure automation; complementary to n8n)
- ADR 0057: Mattermost (notification destination for n8n workflows)
- ADR 0058: NATS event bus (n8n bridge for external events)
- ADR 0124: Platform event taxonomy (n8n publishes compliant events)
- ADR 0132: Self-describing platform manifest (daily digest source)
- ADR 0147: Vaultwarden (source of credentials for n8n integrations)
