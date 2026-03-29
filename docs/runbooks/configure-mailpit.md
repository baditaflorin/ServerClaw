# Configure Mailpit

## Purpose

This runbook converges the private Mailpit SMTP interceptor from ADR 0282 and
verifies the guest-network HTTP and SMTP capture path end to end.

## Result

- `docker-runtime-lv3` runs Mailpit from `/opt/dev-tools/mailpit`
- Mailpit listens privately on `10.10.10.20:8025` for the UI and REST API
- Mailpit listens privately on `10.10.10.20:1025` for unauthenticated SMTP capture
- staging and other non-production SMTP-aware automation can point at `mailpit`
  on the `dev-tools_default` Docker network instead of the production Stalwart relay

## Commands

Syntax-check the Mailpit workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-mailpit
```

Converge the Mailpit runtime directly:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-mailpit env=production
```

Run the governed live-apply wrapper:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=mailpit env=production
```

## Verification

Verify the private Mailpit info endpoint on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'curl -fsS http://127.0.0.1:8025/api/v1/info'
```

Verify Mailpit captures an SMTP probe through the REST API:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'python3 - <<'"'"'PY'"'"'
import json
import smtplib
import urllib.request
from email.message import EmailMessage

subject = "LV3 Mailpit runbook verification"
urllib.request.urlopen(
    urllib.request.Request("http://127.0.0.1:8025/api/v1/messages", method="DELETE"),
    timeout=30,
).read()

message = EmailMessage()
message["From"] = "runbook-check@lv3.org"
message["To"] = "mailpit-runbook@lv3.org"
message["Subject"] = subject
message.set_content("Runbook verification through Mailpit")

with smtplib.SMTP("127.0.0.1", 1025, timeout=15) as client:
    client.send_message(message)

payload = json.loads(
    urllib.request.urlopen("http://127.0.0.1:8025/api/v1/messages", timeout=30).read().decode("utf-8")
)
assert any(item.get("Subject") == subject for item in payload.get("messages", []))
print("verified")
PY'
```

Verify the staging mail-verification playbook still syntax-checks with the Mailpit path:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ansible-playbook -i inventory/hosts.yml playbooks/mail-platform-verify.yml \
  --private-key .local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump \
  -e env=staging \
  --syntax-check
```

## Operating Notes

- Mailpit is intentionally private-only. Do not publish it on the public NGINX edge.
- Mailpit is intentionally stateless. Restarting or re-creating the container clears captured messages.
- Production mail delivery must continue to point at Stalwart; Mailpit is only for staging,
  development, and assertion-level verification traffic.
