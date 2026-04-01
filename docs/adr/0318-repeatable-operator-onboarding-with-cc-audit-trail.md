# ADR 0318: Repeatable Operator Onboarding with CC Audit Trail

- Status: Accepted
- Implementation Status: Implemented
- Date: 2026-04-01
- Implemented In Repo Version: 0.0.0
- Tags: operator-provisioning, iac, email, audit-trail, llm-agent

## Context

ADR 0108 designs a Windmill-backed operator onboarding workflow. ADR 0317 documents the
Keycloak direct-API fallback when Windmill is unavailable. Both ADRs stop at account
creation: they do not codify the **email delivery format**, do not require a
**copy to the requester**, and do not provide a **single callable script** that an LLM
agent can discover and run without reading multiple ADRs.

Two gaps became clear during real provisioning sessions:

1. **No audit trail for the requester.** When an agent provisions an account there is no
   automatic record sent to the person who asked for it. The requester must check
   `.local/keycloak/<username>-password.txt` manually to confirm provisioning succeeded.

2. **No canonical IaC entry point.** Agents must reconstruct the provisioning sequence
   from prose in ADR 0317. A misstep (wrong admin username, token expiry, wrong lastName
   characters) silently fails or breaks mid-flow with no retry logic.

This ADR codifies:
- A canonical Python script (`scripts/provision_operator.py`) as the single entry point
  for operator provisioning.
- A standardised onboarding email template with **CC to the requester** as a mandatory
  audit record.
- The `operators.yaml` update procedure that must follow provisioning.

## Decision

### 1. Canonical provisioning script

`scripts/provision_operator.py` is the authoritative IaC entry point for operator
onboarding. It wraps ADR 0317's Keycloak direct-API procedure and adds email delivery.

**Invocation:**

```bash
python3 scripts/provision_operator.py \
    --id matei-busui-tmp-001 \
    --name "Matei Busui" \
    --email busui.matei1994@gmail.com \
    --username matei.busui-tmp \
    --role admin \
    --expires 2026-04-08T00:00:00Z \
    --requester florin@badita.org
```

**What the script does (idempotent):**

| Step | Action |
|------|--------|
| 0 | Check `.local/keycloak/<username>-password.txt` — reuse if exists, generate if not |
| 1 | Check if Keycloak user already exists (skip creation if yes) |
| 2 | Create Keycloak user with credentials |
| 3 | Assign realm roles (derived from `--role` tier; see table below) |
| 4 | Assign groups (derived from `--role` tier) |
| 5 | Verify role and group assignments |
| 6 | Send onboarding email to operator **CC requester** |

The script is safe to run twice: re-running skips creation, re-sends the email.

### 2. Role tier → Keycloak mappings

| `--role` | Realm role | Groups | OpenBao policy |
|---|---|---|---|
| `admin` | `platform-admin` | `lv3-platform-admins`, `grafana-admins` | `platform-admin` |
| `operator` | `platform-operator` | `lv3-platform-operators` | `platform-operator` |
| `viewer` | `platform-viewer` | `lv3-platform-viewers` | `platform-read` |

### 3. CC-to-requester email as mandatory audit record

Every onboarding email MUST be CC'd to the requester (`--requester` argument). This
creates an automatic audit trail:

- The requester has proof that provisioning succeeded.
- The operator's inbox is evidence of access grant time.
- No side-channel (Mattermost, Slack) is needed to confirm provisioning.

The email includes:
- SSO login URL, username, and password
- Service directory with links to all platform services
- SSH access setup instructions (step-ca + Tailscale)
- Codebase tour for programmer onboardees
- Expiry date and renewal contact

### 4. `operators.yaml` update (always follows provisioning)

After running the script, add an entry to `config/operators.yaml` and push to
`origin/main`. The schema is enforced by `config/schemas/operators.schema.json`.

Minimum required fields:

```yaml
- id: <id>                        # unique slug, e.g. matei-busui-tmp-001
  name: <Full Name>
  email: <email>
  role: admin | operator | viewer
  status: active
  keycloak:
    username: <keycloak-username>
    realm_roles: [<role-from-table-above>]
    groups: [<groups-from-table-above>]
    enabled: true
  ssh:
    principal: <keycloak-username>
    certificate_ttl_hours: 24
    public_keys: []               # empty until operator registers their key
  openbao:
    entity_name: <keycloak-username>
    policies: [<policy-from-table-above>]
  tailscale:
    login_email: <email>
    tags: [tag:platform-operator]
  audit:
    onboarded_at: '<ISO8601-timestamp>'
    onboarded_by: <agent-or-person-id>
  notes: "EPHEMERAL ... Expires <date>."
```

For temporary accounts, add `Expires <date>` in the `notes` field.

### 5. Dry-run mode

The script supports `--dry-run` to validate inputs and print what would happen without
touching Keycloak or sending email:

```bash
python3 scripts/provision_operator.py ... --dry-run
```

## Infrastructure requirements

| Requirement | How it is met |
|---|---|
| Keycloak admin API | `lv3-bootstrap-admin` credentials in `.local/keycloak/bootstrap-admin-password.txt` |
| SMTP relay | Internal host `10.10.10.20:587`; script SSH-proxies via `ops@100.64.0.1` |
| SSH proxy key | `.local/ssh/hetzner_llm_agents_ed25519` |
| Token TTL | Script re-authenticates per Keycloak call (60-second token lifetime) |

All secrets live in `.local/` (gitignored). No secrets are committed to the repository.

## LLM agent discovery hints

When an agent needs to provision an operator account:

```bash
# 1. Find this script
ls scripts/provision_operator.py

# 2. Read the docstring
python3 scripts/provision_operator.py --help

# 3. Check what credentials exist
ls .local/keycloak/*-password.txt

# 4. Run dry-run first
python3 scripts/provision_operator.py \
    --id <id> --name "<name>" --email <email> \
    --username <kc-username> --role admin \
    --expires <ISO8601> --requester <your-email> \
    --dry-run

# 5. Run for real
python3 scripts/provision_operator.py ... # without --dry-run

# 6. Add operators.yaml entry, commit, push
```

## Consequences

**Positive**

- A single command provisions a complete operator account: Keycloak user, role, groups,
  email with credentials — no manual steps.
- The CC-to-requester pattern creates an automatic, time-stamped audit record without
  requiring a separate audit log write.
- Idempotency means the script can be re-run safely if something fails mid-way.
- `--dry-run` makes the script safe to test in CI or during agent planning.
- LLM agents can discover and execute the full flow from a single ADR + script, without
  reading ADR 0108, 0307, and 0317 sequentially.

**Negative / Trade-offs**

- The script does **not** provision OpenBao policies or step-ca SSH certificates (requires
  Docker network access via `operator_manager.py` — see ADR 0308). Temporary admin
  accounts via Keycloak SSO alone are sufficient for the common use case.
- The SMTP relay requires SSH proxy access. If `100.64.0.1` is unreachable, email
  delivery fails; the Keycloak account is still created. The password file at
  `.local/keycloak/<username>-password.txt` remains the fallback.
- Keycloak tokens expire in 60 seconds. The script re-authenticates per call, adding
  ~1 second of latency per step.

## Related ADRs

- ADR 0108: Operator onboarding/offboarding workflow (full Windmill design)
- ADR 0307: Temporary operator account schema and expiry conventions
- ADR 0308: Why `operator_manager.py` cannot run from outside the Docker network
- ADR 0317: Keycloak direct-API provisioning step-by-step procedure
- ADR 0042: step-ca for SSH certificate issuance (SSH setup referenced in onboarding email)
- ADR 0056: Keycloak SSO (identity layer this script targets)
