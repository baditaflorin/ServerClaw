# ADR 0307: Temporary Guest Operator Accounts With 72-Hour Expiry

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.0.0
- Implemented In Platform Version: 0.0.0
- Implemented On: 2026-03-31
- Date: 2026-03-31

## Context

The operator onboarding workflow (ADR 0108) is designed for permanent platform operators with ongoing responsibilities. It provisions full Keycloak, step-ca SSH, OpenBao, and Tailscale access, with offboarding as an explicit manual action.

Two recurring scenarios are not well served by this model:

1. **Short-lived collaboration with full access**: A guest collaborator, external helper, or temporary pair-programmer needs full admin login access to all platform services for a bounded period (hours to a few days). Provisioning them as a permanent operator and relying on a manual offboard is error-prone — the offboard step is routinely forgotten.

2. **LLM agent or automated task access**: An agent working a time-boxed task needs scoped access that self-expires without human intervention.

The current `operators.yaml` schema (v1.0.0) has no `expires_at` field. There is no automated reaper for expired operators analogous to the VM reaper defined in ADR 0106. As a result, temporary access either does not get created (blocking collaboration) or does not get cleaned up (creating stale access).

## Decision

Temporary operators are full participants in the ADR 0108 onboarding model — same Keycloak SSO, step-ca SSH certificates, OpenBao secrets access, and Tailscale network access as permanent operators. The only distinction is a mandatory expiry date encoded in the `notes` field and, eventually, a dedicated `audit.expires_at` field once the schema is extended.

### Role assignment for temporary accounts

Temporary accounts use the same three roles as permanent operators. The role is chosen based on what the guest actually needs, **not** defaulted to viewer:

| Scenario | Role |
|---|---|
| Full service login, admin UI access, SSH to VMs | `admin` |
| Deploy and operate but no secret management | `operator` |
| Monitoring and log review only | `viewer` |

Most short-term collaborators who need to "log in to the different services" should be given `admin` role — matching the access of `florin-badita`. Granting a lower role and then escalating ad-hoc is worse than starting with the right access and revoking it cleanly at expiry.

### Immediate: encode expiry in `notes`

Until the schema and reaper are extended, temporary operators are created using the standard `operators.yaml` schema with the expiry date written explicitly in the `notes` field:

```yaml
- id: guest-tmp-001
  name: Temporary Admin Guest
  email: guest-tmp-001@platform.local
  role: admin
  status: active
  notes: |
    Temporary 72-hour admin account. Expires 2026-04-03T00:00:00Z.
    Created per ADR 0307. Full service login access (Keycloak SSO, Grafana, OpenBao, Tailscale, SSH).
    MUST be offboarded at expiry: set status=inactive and run operator-offboard workflow.
    Replace email and public_keys with real collaborator details before running onboard workflow.
  keycloak:
    username: guest-tmp-001
    realm_roles:
      - platform-admin
    groups:
      - lv3-platform-admins
      - grafana-admins
    enabled: true
  ssh:
    principal: guest-tmp-001
    certificate_ttl_hours: 24
    public_keys: []
  openbao:
    entity_name: guest-tmp-001
    policies:
      - platform-admin
  tailscale:
    login_email: guest-tmp-001@platform.local
    tags:
      - tag:platform-operator
  audit:
    onboarded_at: "2026-03-31T00:00:00Z"
    onboarded_by: adr-0307-tmp-user
```

**Rules for temporary accounts:**

| Field | Requirement |
|---|---|
| `id` | `guest-tmp-NNN` or `<name>-tmp-NNN` — never a permanent-style id |
| `notes` line 1 | Must be `Temporary <duration> <role> account. Expires <ISO-8601 datetime>.` |
| `email` | Replace placeholder with real collaborator email before running `operator-onboard` |
| `ssh.public_keys` | Empty until the collaborator provides their actual public key |
| `audit.onboarded_by` | Reference the ADR or ticket that authorised the access |

### Checklist before running the onboard workflow

1. Replace `email: guest-tmp-001@platform.local` with the collaborator's real email address
2. Add their SSH public key under `ssh.public_keys` (or leave empty if SSH access is not needed)
3. Confirm the role is correct (`admin` for full service login)
4. Run: `lv3 operator add --from-yaml config/operators.yaml --id guest-tmp-001`

### Near-term: extend the schema with `expires_at`

The `operators.schema.json` should be extended to support an optional `expires_at` field on the `audit` object:

```json
"audit": {
  "properties": {
    "expires_at": {
      "type": "string",
      "format": "date-time",
      "description": "If set, the operator must be offboarded at or before this time."
    }
  }
}
```

A nightly Windmill workflow `operator-expiry-reaper` will:

1. Load `config/operators.yaml`
2. For each operator where `audit.expires_at` is in the past and `status == active`:
   a. Run the `operator-offboard` workflow (same as ADR 0108)
   b. Post a Mattermost notification: `Temporary operator <id> expired at <time>. Access revoked automatically.`
3. Operators expiring within the next 24 hours trigger a warning notification to allow for extension if needed.

### Naming convention for LLM-agent lookup

Any future LLM agent or automation that needs to find or audit temporary users should:

1. Check `config/operators.yaml` for entries where `id` matches `*-tmp-*` or where `notes` contains `Expires`.
2. Parse the expiry from `notes` (pattern: `Expires <ISO-8601>`) or `audit.expires_at` (once schema is extended).
3. Compare against current time — flag `status == active` entries past their expiry for offboarding.

**Search hints for agents:**
```bash
# Find all temporary accounts and their deadlines
grep -A2 "Expires" config/operators.yaml

# Find all tmp-pattern IDs
grep "id: .*-tmp-" config/operators.yaml
```

## Consequences

**Positive**
- Temporary full-admin access can be granted immediately using the existing schema and onboarding workflow
- The `notes` expiry convention is machine-readable for both humans and LLM agents without schema changes
- All temporary accounts inherit the full audit trail from ADR 0108 (onboarded_at, onboarded_by, offboarded_at)
- Giving the correct role upfront (admin) avoids ad-hoc privilege escalation during the collaboration window

**Negative / Trade-offs**
- Temporary `admin` accounts have the same access as permanent admins; offboarding at expiry is critical — for admin role, the offboard workflow also flags secrets for rotation (ADR 0108 behaviour)
- Until `expires_at` is in the schema and the reaper is running, expiry is advisory only; a human must run the offboard workflow manually
- A `notes`-based expiry is fragile if edited carelessly; the schema extension is the durable fix
- `platform-admin` Keycloak group and OpenBao policy must exist before provisioning; the onboard workflow will fail if they do not

## Alternatives Considered

- **Share the admin's credentials temporarily**: no audit trail, not selectively revocable, exposes the owner's personal credentials.
- **Provision as `viewer` by default**: forces ad-hoc escalation during the session; better to grant the right role upfront with a hard expiry.
- **Create a one-off Linux user with `useradd --expiredate`**: bypasses the unified access model — no Keycloak SSO, no Grafana, no OpenBao, not revocable via a single command.
- **Use step-ca certificate TTL as the only expiry**: covers SSH only; Keycloak and OpenBao access remains active; the collaborator must renew SSH every 24h within a 72h window.

## Implementation Notes

The first temporary account created under this ADR is `florin-tmp-001` in `config/operators.yaml`:

- Provisioned: 2026-03-31
- Expires: 2026-04-03T00:00:00Z (72 hours)
- Email: florin@badita.org
- Role: `admin` — full login access to Keycloak SSO, Grafana, OpenBao, Tailscale, and SSH (once a public key is added)

To offboard when the 72-hour window closes:

```bash
lv3 operator remove --id florin-tmp-001
```

Or manually: set `status: inactive` in `operators.yaml` and run the `operator-offboard` Windmill workflow. Because this is an `admin` account, the offboard workflow will also flag all platform secrets for rotation.

## Related ADRs

- ADR 0046: Identity classes (temporary guest is a subset of the Human Operator class)
- ADR 0106: Ephemeral environment lifecycle (analogous time-limited resource pattern)
- ADR 0108: Operator onboarding and off-boarding (the workflow temporary accounts use)
- ADR 0141: API token lifecycle (credential expiry patterns reused here)
- ADR 0267: Expiring gate bypass waivers (another time-bounded access pattern in this platform)
