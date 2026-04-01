# ADR 0317: Keycloak Direct-API Operator Provisioning via SSH Proxy

- Status: Accepted
- Implementation Status: Complete
- Date: 2026-04-01
- Implemented In Repo Version: 0.0.0
- Tags: operator-provisioning, keycloak, llm-agent, identity

## Context

ADR 0307 defines the pattern for temporary operator accounts, and ADR 0308 documents why running
`operator_manager.py` from the Mac fails (OpenBao mTLS, Windmill SSO redirect). This ADR codifies
the **working fallback path**: provisioning Keycloak accounts directly via its admin REST API
through the SSH proxy host, without needing Windmill, OpenBao client certs, or Docker access.

### Discovery path for LLM agents

When you arrive at this repository and need to provision a Keycloak user, run this check first:

```bash
# 1. SSH access works?
ssh -i .local/ssh/hetzner_llm_agents_ed25519 ops@100.64.0.1 "echo ok"

# 2. Keycloak admin API works?
curl -sk https://sso.lv3.org/realms/master/protocol/openid-connect/token \
  -d "client_id=admin-cli&grant_type=password&username=lv3-bootstrap-admin&password=$(cat .local/keycloak/bootstrap-admin-password.txt | python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))')" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK, expires_in:', d.get('expires_in'))"
```

If both succeed, use this ADR's procedure. If Keycloak returns 502, wait 30 s and retry — the
container restarts occasionally.

## Critical facts

| Item | Value |
|---|---|
| Keycloak public URL | `https://sso.lv3.org` |
| Admin bootstrap username | `lv3-bootstrap-admin` |
| Admin bootstrap password file | `.local/keycloak/bootstrap-admin-password.txt` |
| Target realm | `lv3` |
| Token TTL | **60 seconds** — get a fresh token for every curl call |
| SSH proxy host | `ops@100.64.0.1` via `.local/ssh/hetzner_llm_agents_ed25519` |
| Transactional SMTP | `10.10.10.20:587`, login `platform`, password `.local/mail-platform/profiles/platform-transactional-mailbox-password.txt` |
| Sender address | `platform@lv3.org` |
| Existing user passwords | `.local/keycloak/<username>-password.txt` (check here before generating new) |

**Why `admin-cli` only works in the master realm:** `admin-cli` is a public client in `master`
but not in `lv3`. Use the master-realm token to call `/admin/realms/lv3/` endpoints.

**Why Windmill redirects:** Windmill is configured with Keycloak OIDC SSO — its `/api/auth/login`
endpoint returns 302 to `sso.lv3.org`, blocking programmatic API access without a browser flow.

## Decision

LLM agents MUST use the Keycloak admin REST API directly for operator provisioning when
`operator_manager.py` is blocked. The procedure below is the canonical fallback path.

## Procedure

### Step 0 — Check for existing password file

```bash
ls .local/keycloak/ | grep "<username>"
# If florin.badita-password.txt exists, the password is already recorded — use it.
```

### Step 1 — Acquire admin token (60-second TTL)

```bash
TOKEN=$(curl -sk https://sso.lv3.org/realms/master/protocol/openid-connect/token \
  -d "client_id=admin-cli&grant_type=password&username=lv3-bootstrap-admin&password=$(cat .local/keycloak/bootstrap-admin-password.txt | python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))')" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

> **Tip:** Token expires in 60 s. For multi-step flows, wrap each curl in a fresh TOKEN assignment
> or use a Python script that re-authenticates per call.

### Step 2 — Check if user already exists

```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://sso.lv3.org/admin/realms/lv3/users?username=<username>&exact=true" \
  | python3 -c "import sys,json; users=json.load(sys.stdin); print(f'Found {len(users)} user(s)')"
```

### Step 3 — Create the user

```bash
PASS="$(python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(24)).decode())")"

curl -sk -w "\nHTTP:%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://sso.lv3.org/admin/realms/lv3/users" \
  -d "{
    \"username\": \"<username>\",
    \"email\": \"<email>\",
    \"firstName\": \"<FirstName>\",
    \"lastName\": \"<LastName>\",
    \"enabled\": true,
    \"emailVerified\": true,
    \"credentials\": [{\"type\": \"password\", \"value\": \"$PASS\", \"temporary\": false}]
  }"
# Expect HTTP:201 on success. Note: parentheses in lastName cause HTTP:400 — use plain text.
```

Save the password immediately: `echo "$PASS" > .local/keycloak/<username>-password.txt`

### Step 4 — Get user ID

```bash
USER_ID=$(curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://sso.lv3.org/admin/realms/lv3/users?username=<username>&exact=true" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")
```

### Step 5 — Assign realm roles

```bash
# Get role details
ROLE=$(curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://sso.lv3.org/admin/realms/lv3/roles/<role-name>")
ROLE_ID=$(echo "$ROLE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
ROLE_NAME=$(echo "$ROLE" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")

# Assign role (expect HTTP:204)
curl -sk -w "HTTP:%{http_code}" -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://sso.lv3.org/admin/realms/lv3/users/$USER_ID/role-mappings/realm" \
  -d "[{\"id\":\"$ROLE_ID\",\"name\":\"$ROLE_NAME\"}]"
```

Role names per access tier (from `scripts/operator_manager.py`):

| Role | Keycloak realm role | Groups |
|---|---|---|
| `admin` | `platform-admin` | `lv3-platform-admins`, `grafana-admins` |
| `operator` | `platform-operator` | `lv3-platform-operators` |
| `viewer` | `platform-viewer` | `lv3-platform-viewers` |

### Step 6 — Assign groups

```bash
# List all groups to find IDs
curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://sso.lv3.org/admin/realms/lv3/groups?max=100" \
  | python3 -c "import sys,json; [print(g['id'], g['name']) for g in json.load(sys.stdin)]"

# Add user to group (expect HTTP:204)
curl -sk -w "HTTP:%{http_code}" -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  "https://sso.lv3.org/admin/realms/lv3/users/$USER_ID/groups/<group-id>"
```

### Step 7 — Send welcome email via SMTP

Keycloak does not automatically send welcome emails in this configuration. Send credentials
manually via the platform transactional SMTP server. The script below runs from the SSH proxy:

```bash
# Copy script to proxy host and run
ssh -i .local/ssh/hetzner_llm_agents_ed25519 ops@100.64.0.1 python3 << 'PYEOF'
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

msg = MIMEMultipart('alternative')
msg['Subject'] = '[lv3.org] Platform account credentials'
msg['From'] = 'LV3 Platform <platform@lv3.org>'
msg['To'] = '<recipient-email>'
msg['Reply-To'] = 'ops@lv3.org'
msg.attach(MIMEText(
    "Login URL:  https://sso.lv3.org\n"
    "Username:   <username>\n"
    "Password:   <password>\n", 'plain'))

with smtplib.SMTP('10.10.10.20', 587, timeout=10) as s:
    s.ehlo()
    if s.has_extn('STARTTLS'):
        s.starttls(); s.ehlo()
    s.login('platform', '<platform-mailbox-password>')
    s.sendmail('platform@lv3.org', ['<recipient-email>'], msg.as_string())
    print('sent')
PYEOF
```

SMTP password is in `.local/mail-platform/profiles/platform-transactional-mailbox-password.txt`.

### Step 8 — Verify

```bash
TOKEN=$(...)  # fresh token
USER_ID="<id>"
curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://sso.lv3.org/admin/realms/lv3/users/$USER_ID/role-mappings/realm" \
  | python3 -c "import sys,json; print([r['name'] for r in json.load(sys.stdin)])"
curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://sso.lv3.org/admin/realms/lv3/users/$USER_ID/groups" \
  | python3 -c "import sys,json; print([g['name'] for g in json.load(sys.stdin)])"
```

## Common failures and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `invalid_grant` on master realm token | Wrong username or password | Username is `lv3-bootstrap-admin`, not `admin` |
| HTTP:502 from sso.lv3.org | Keycloak container restarting | Wait 30 s, retry |
| `invalid_grant` on lv3 realm with `admin-cli` | `admin-cli` not a public client in lv3 | Use master realm token for all `/admin/realms/lv3/` API calls |
| HTTP:400 `error-person-name-invalid-character` | Parentheses or special chars in firstName/lastName | Use plain ASCII only (e.g. `"Badita Tmp"` not `"Badita (Temporary)"`) |
| Token expired mid-script | 60-second TTL | Get fresh token per curl call or use a Python script |
| Windmill API returns 302 | SSO redirect | Do not use Windmill API for auth; use Keycloak admin API directly |

## Relationship to ADR 0307 / ADR 0308

- **ADR 0307** — defines operator account schema (`config/operators.yaml`), expiry conventions, and role tiers. Always update `operators.yaml` first.
- **ADR 0308** — explains why `operator_manager.py` cannot run from Mac (OpenBao mTLS, no Docker access). This ADR is the working alternative.
- **This ADR (0317)** — is the actionable step-by-step procedure that fills the gap ADR 0308 documented.

## LLM agent search hints

```bash
# Find Keycloak admin password
cat .local/keycloak/bootstrap-admin-password.txt

# Find existing user passwords (check before generating new)
ls .local/keycloak/*-password.txt

# Find SMTP credentials
cat .local/mail-platform/profiles/platform-transactional-mailbox-password.txt

# Discover which groups exist in Keycloak (requires token)
# See Step 6 above

# Quick health check
curl -sk -o /dev/null -w '%{http_code}' https://sso.lv3.org/realms/lv3
# 200 = up, 502 = restarting (retry in 30s)
```

## Consequences

- LLM agents can provision Keycloak users without Windmill, Docker access, or OpenBao client certs.
- The SMTP path (Step 7) ensures credentials reach users even when Keycloak's built-in email is unconfigured.
- The 60-second token TTL is a hard constraint — scripts must be written to re-authenticate.
- This procedure does NOT provision OpenBao policies or SSH certificates; those require `operator_manager.py` from inside the Docker network. For temporary admin accounts, Keycloak SSO access alone is sufficient for the login use case.
