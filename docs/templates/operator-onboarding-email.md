# Operator Onboarding Email Template

Copy and customize this template when sending account credentials manually
(e.g. via Gmail draft when the automated SMTP path is unavailable).

---

## Subject Line

```
[example.com] Platform access — <FIRST_NAME> — expires <EXPIRY_DATE>
```

## Body (plain text)

```
Hi <FIRST_NAME>,

Your new temporary <ROLE> account on the example.com homelab platform is ready.
Valid until <EXPIRY_ISO8601>.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 YOUR SSO CREDENTIALS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Login portal : https://sso.example.com
  Username     : <KEYCLOAK_USERNAME>
  Password     : <GENERATED_PASSWORD>
  Expires      : <EXPIRY_ISO8601>

Change your password: https://sso.example.com/realms/lv3/account/

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PLATFORM SERVICES  (all use SSO)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Grafana  (metrics)       https://grafana.example.com
  Gitea    (source code)   https://gitea.example.com
  Outline  (docs/wiki)     https://outline.example.com
  Vikunja  (tasks)         https://vikunja.example.com
  Open WebUI (AI)          https://chat.example.com
  Mattermost (chat)        https://mattermost.example.com
  Harbor (registry)        https://harbor.example.com
  Windmill (workflows)     https://windmill.example.com

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 VPN ACCESS (Tailscale / Headscale)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 1. Install Tailscale
  brew install tailscale          # macOS
  curl -fsSL https://tailscale.com/install.sh | sh   # Linux

  # 2. Connect (pre-auth key valid until <EXPIRY_ISO8601>)
  sudo tailscale up \
    --login-server https://headscale.example.com \
    --authkey <HEADSCALE_AUTHKEY> \
    --hostname <USERNAME>-laptop

  tailscale status    # verify — you'll get a 100.x.x.x address

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 SSH ACCESS (step-ca certificates, 24h TTL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 1. Install Smallstep CLI
  brew install step               # macOS

  # 2. Bootstrap the CA (one-time)
  step ca bootstrap \
    --ca-url https://ca.example.com \
    --fingerprint <CA_FINGERPRINT>

  # 3. Follow docs/runbooks/operator-onboarding.md for SSH cert setup

  # 4. SSH in (requires Tailscale)
  ssh <USERNAME>@100.64.0.1

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 QUICK CHECKLIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  □ Log in at https://sso.example.com and change your password
  □ Install Tailscale and connect via Headscale
  □ Bootstrap step-ca for SSH certificates
  □ Browse https://grafana.example.com for platform dashboards

Account expires <EXPIRY_ISO8601>.

Welcome aboard,
example.com platform (provisioned per ADR 0318)
---
CC: <REQUESTER_EMAIL> — audit record per ADR 0318.
```

## Placeholders Reference

| Placeholder | Source |
|-------------|--------|
| `<FIRST_NAME>` | From request |
| `<ROLE>` | `admin`, `operator`, or `viewer` |
| `<KEYCLOAK_USERNAME>` | `<first>.<last>-tmp-NNN` |
| `<GENERATED_PASSWORD>` | `.local/keycloak/<username>-password.txt` |
| `<EXPIRY_ISO8601>` | Computed from duration |
| `<HEADSCALE_AUTHKEY>` | `.local/headscale/<username>-authkey.txt` |
| `<CA_FINGERPRINT>` | `openssl x509 -noout -fingerprint -sha256 -in .local/step-ca/certs/root_ca.crt` |
| `<REQUESTER_EMAIL>` | Person who authorized the access |

## When to Use This Template

- Keycloak API is unreachable and you created the user manually via Keycloak admin UI
- The automated `provision_operator.py --skip-email` was used and email needs to be sent separately
- Gmail MCP draft is the preferred delivery method (faster than SSH-proxied SMTP)
