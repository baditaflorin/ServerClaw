# Configure Mail Platform

## Purpose

This runbook converges the LV3 mail platform defined by ADR 0041 and the sender-profile layer from ADR 0050.

It covers:

- public DNS for `mail.lv3.org` and the `lv3.org` MX record
- host-side SMTP and IMAPS forwarding on the Proxmox host
- the Stalwart mail runtime on `docker-runtime-lv3`
- a private SMTP submission relay on `10.10.10.20:1587` for local platform workloads such as Keycloak
- the private mail gateway API used by platform services and automation agents
- profile-scoped sender identities for operator alerts, platform transactional mail, and agent reports
- Telegraf and Grafana mail telemetry
- OpenTelemetry traces from the mail gateway into the shared monitoring collector

## Preconditions

Before running the workflow, confirm:

1. `server@lv3.org` is the desired managed mailbox and the three default notification profiles should exist:
   - `alerts@lv3.org`
   - `platform@lv3.org`
   - `agents@lv3.org`
2. the public IP `65.108.75.123` can receive SMTP traffic on TCP `25`, `587`, and `993`
3. `HETZNER_DNS_API_TOKEN` is set on the controller
4. `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/brevo-api-key.txt` exists and contains the Brevo transactional API key
5. the sender configured in Brevo is valid for transactional sends

## Entrypoints

- syntax check: `make syntax-check-mail-platform`
- preflight: `make preflight WORKFLOW=converge-mail-platform`
- converge: `HETZNER_DNS_API_TOKEN=... make converge-mail-platform`

## Delivered Surfaces

The workflow manages these live surfaces:

- `mail.lv3.org` A record
- `lv3.org` MX record pointing at `mail.lv3.org`
- SPF and DMARC TXT records for `lv3.org`
- Proxmox host NAT forwards for TCP `25`, `587`, and `993` to `docker-runtime-lv3`
- Stalwart mail server on `docker-runtime-lv3`
- private submission relay on `10.10.10.20:1587` for local platform workloads on `docker-runtime-lv3`
- private mail gateway API on `docker-runtime-lv3:8081`
- scoped notification-profile API keys under `/etc/lv3/mail-platform/profiles/`
- Telegraf mail telemetry collector on `docker-runtime-lv3`
- Grafana dashboard `lv3-mail-platform` on `monitoring-lv3`
- mail-gateway traces exported to Tempo through `http://10.10.10.40:4318/v1/traces`

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/stalwart-admin-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/server-mailbox-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/metrics-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/gateway-api-key.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/profiles/operator-alerts-mailbox-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/profiles/operator-alerts-gateway-api-key.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/profiles/platform-transactional-mailbox-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/profiles/platform-transactional-gateway-api-key.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/profiles/agent-reports-mailbox-password.txt`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/profiles/agent-reports-gateway-api-key.txt`

## Private Mail API

The mail gateway is the stable automation entrypoint for sends plus mailbox, domain, and notification-profile discovery.

Base URL from the private LV3 network:

- `http://10.10.10.20:8081`

The same converge also publishes a private SMTP submission relay for local platform workloads:

- `10.10.10.20:1587`

That relay is intended for repo-managed services running on `docker-runtime-lv3`, such as Keycloak password-reset mail. Public client submission remains on TCP `587`.

Authentication:

- admin header: `X-API-Key: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/gateway-api-key.txt)`
- scoped send header example: `X-API-Key: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/profiles/platform-transactional-gateway-api-key.txt)`

Admin credentials can list domains, mailboxes, gateway state, and all notification profiles.

Profile-scoped credentials can only:

- list their own notification profile metadata
- send mail as that profile's fixed sender identity

The current default profiles are:

1. `operator-alerts` -> `alerts@lv3.org`
2. `platform-transactional` -> `platform@lv3.org`
3. `agent-reports` -> `agents@lv3.org`

Useful operations:

1. Send mail

```sh
curl -s \
  -H "X-API-Key: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/profiles/platform-transactional-gateway-api-key.txt)" \
  -H "Content-Type: application/json" \
  -d '{"to":["baditaflorin@gmail.com"],"subject":"LV3 mail test","text":"mail platform is live"}' \
  http://10.10.10.20:8081/send
```

2. List notification profiles

```sh
curl -s \
  -H "X-API-Key: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/gateway-api-key.txt)" \
  http://10.10.10.20:8081/v1/profiles
```

3. List domains

```sh
curl -s \
  -H "X-API-Key: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/gateway-api-key.txt)" \
  http://10.10.10.20:8081/v1/domains
```

4. Ensure the managed mailbox exists

```sh
curl -s \
  -X PUT \
  -H "X-API-Key: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/gateway-api-key.txt)" \
  -H "Content-Type: application/json" \
  -d '{"emails":["server@lv3.org"]}' \
  http://10.10.10.20:8081/v1/mailboxes/server
```

## Verification

Run these checks after converge:

1. `make syntax-check-mail-platform`
2. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'docker compose --file /opt/mail-platform/docker-compose.yml ps && sudo ls -l /opt/mail-platform/openbao /run/lv3-secrets/mail-platform && sudo test ! -e /opt/mail-platform/gateway/gateway.env'`
3. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'python3 /usr/local/libexec/lv3-mail-platform-metrics.py'`
4. `curl -s -H "X-API-Key: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/gateway-api-key.txt)" http://10.10.10.20:8081/v1/profiles`
5. `curl -s -H "X-API-Key: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/mail-platform/gateway-api-key.txt)" http://10.10.10.20:8081/v1/mailboxes`
6. `ansible-playbook -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/mail-platform-notification-profiles-verify.yml --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump --limit docker-runtime-lv3`
7. `curl -I https://grafana.lv3.org`
8. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.40 'curl -fsS http://127.0.0.1:3200/api/search/tag/service.name/values | jq -r ''.tagValues[]'' | grep mail-gateway'`
9. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.118.189.95 ops@10.10.10.20 'python3 - <<'"'"'PY'"'"'\nimport smtplib\nfrom pathlib import Path\npassword = Path(\"/etc/lv3/mail-platform/server-mailbox-password\").read_text().strip()\nclient = smtplib.SMTP(\"10.10.10.20\", 1587, timeout=10)\nclient.ehlo()\nprint(client.login(\"server\", password))\nclient.quit()\nPY'`

## Notes

- inbound mail for `server@lv3.org` depends on the public MX record and host NAT being active
- outbound transactional delivery currently uses the Brevo HTTP API from the mail gateway
- the private SMTP submission relay on TCP `1587` exists specifically for local platform workloads that need authenticated mail without depending on public STARTTLS certificate trust
- sender governance is enforced through notification-profile-specific mailbox identities and scoped API keys instead of one shared global send credential
- the first distributed traces for this workflow come from inbound gateway requests plus outbound HTTP calls to Stalwart and Brevo, with `service.namespace=lv3` and `deployment.environment=lv3` exported through `OTEL_RESOURCE_ATTRIBUTES`
- if direct public SMTP delivery from one profile is required later, add the sender identity, DKIM, and reverse-DNS path explicitly for that profile instead of reusing broad relay assumptions
