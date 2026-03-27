# ADR 0108: Operator Onboarding and Off-boarding Workflow

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.177.8
- Implemented In Platform Version: 0.130.29
- Implemented On: 2026-03-27
- Date: 2026-03-23

## Context

The platform was designed and operated by a single person. Every access credential, service account, and SSH key was provisioned for that one person and has never been audited for "what would happen if a second person needed access?" or "what would happen if this operator's laptop was compromised?"

As the platform matures, two scenarios become increasingly likely:

1. **A collaborator needs access**: to help troubleshoot an issue, review a deployment, or contribute to an ADR implementation. Currently, the only way to give someone access is to share credentials manually, which is insecure and has no audit trail.

2. **Access needs to be revoked**: a compromised device, an expired collaboration, or a decommissioned service account. Currently there is no procedure for revoking access across all platform services simultaneously, and no list of where access was granted in the first place.

The platform has all the primitives for a proper access model: Keycloak for identity (ADR 0056), step-ca for SSH certificates (ADR 0042), OpenBao for secrets access (ADR 0043), Tailscale for network access (ADR 0014). What is missing is a **process** that ties them together: a single operation that grants all required access and a single operation that revokes all of it.

## Decision

We will implement a **Windmill-backed operator onboarding and off-boarding workflow** that provisions and revokes access across all platform services atomically, records every grant and revocation in the mutation audit log (ADR 0066), and maintains an `operators.yaml` as the authoritative list of all current human operators.

### Operator roles

Operators are assigned one of three roles:

| Role | Keycloak realm role | SSH access | OpenBao policy | Scope |
|---|---|---|---|---|
| `admin` | `platform-admin` | All VMs | `platform-admin` policy (full read/write) | Full platform control |
| `operator` | `platform-operator` | All VMs | `platform-operator` policy (read + deploy) | Day-to-day platform operations |
| `viewer` | `platform-read` | None | `platform-read` policy (read-only) | Monitoring and observability only |

### `operators.yaml`

The authoritative list of operators lives in `config/operators.yaml`:

```yaml
schema_version: "1.0"
operators:
  - id: florin-admin
    name: Florin
    email: florin@lv3.org
    role: admin
    keycloak_username: florin
    ssh_key_fingerprint: "SHA256:abc123..."
    tailscale_node: "florin-mbp"
    status: active
    onboarded_at: "2024-01-01T00:00:00Z"
    onboarded_by: self
```

This file is the single source of truth. When `operators.yaml` is updated and merged to `main`, the Windmill post-merge workflow automatically applies the changes to all services.

### Onboarding workflow

`lv3 operator add --name "Alice" --email "alice@example.com" --role operator --ssh-key @alice.pub` triggers the Windmill workflow `operator-onboard`:

```python
@windmill_flow(name="operator-onboard")
def onboard_operator(name: str, email: str, role: OperatorRole, ssh_public_key: str):
    # 1. Create Keycloak user and assign realm role
    keycloak_user = create_keycloak_user(
        username=slugify(name),
        email=email,
        realm="lv3",
        roles=[role.keycloak_role]
    )
    send_keycloak_welcome_email(keycloak_user)

    # 2. Register SSH certificate principal in step-ca
    register_ssh_principal(
        user_key=ssh_public_key,
        principal=slugify(name),
        validity="24h"  # operator must renew daily; step ssh login
    )

    # 3. Create OpenBao entity and bind to role policy
    create_openbao_entity(
        name=slugify(name),
        policies=[role.openbao_policy],
        metadata={"email": email, "role": role.value}
    )

    # 4. Provision Tailscale invite (operator must accept)
    tailscale_invite_url = create_tailscale_invite(
        email=email,
        tags=["tag:platform-operator"]
    )

    # 5. Post Mattermost welcome message with next steps
    post_mattermost_welcome(name, tailscale_invite_url, keycloak_user.setup_url)

    # 6. Append to operators.yaml and record in audit log
    append_operator_record(name=name, email=email, role=role, ssh_fingerprint=fingerprint(ssh_public_key))
    record_in_audit_log("operator_onboarded", operator=name, role=role.value)
```

The workflow is idempotent: running it twice for the same operator updates the existing records rather than creating duplicates.

### Off-boarding workflow

`lv3 operator remove --id florin-collab` triggers the Windmill workflow `operator-offboard`:

```python
@windmill_flow(name="operator-offboard")
def offboard_operator(operator_id: str):
    op = load_operator(operator_id)

    # 1. Disable Keycloak user (disable, not delete — preserves audit history)
    disable_keycloak_user(op.keycloak_username)

    # 2. Revoke all active step-ca SSH certificates for this principal
    revoke_ssh_certificates_for_principal(op.ssh_principal)

    # 3. Revoke OpenBao entity (immediately invalidates all tokens)
    revoke_openbao_entity(op.openbao_entity_id)

    # 4. Remove from Tailscale network
    remove_tailscale_device(op.tailscale_node)

    # 5. Rotate any secrets that were visible to this operator
    # (for admin role only — admins have wide OpenBao access)
    if op.role == OperatorRole.ADMIN:
        flag_secrets_for_rotation(reason=f"Admin offboarding: {op.name}")

    # 6. Update operators.yaml status to inactive and record
    mark_operator_inactive(operator_id)
    record_in_audit_log("operator_offboarded", operator=op.name, role=op.role)
    notify_mattermost(f"🔒 Operator {op.name} has been offboarded. All access revoked.")
```

Step-ca SSH certificate revocation takes effect immediately because operators authenticate with short-lived certificates (24h); the current certificate may remain valid for up to 24 hours. For emergency revocation, step-ca's OCSP/CRL support can be used to force immediate revocation.

### Access inventory

`scripts/operator_access_inventory.py` produces a report of all access grants for a given operator:

```
Access inventory for: alice@example.com
  Keycloak: active, realm=lv3, roles=[platform-operator]
  step-ca SSH: 1 active certificate, expires 2026-03-24T12:00:00Z
  OpenBao: entity active, policies=[platform-operator]
  Tailscale: connected, node=alice-mbp, IP=100.x.x.x
  Last seen: 2026-03-23T15:30:00Z (Grafana login)
```

This inventory is used during quarterly access reviews.

### Quarterly access review

A Windmill workflow `quarterly-access-review` runs on the first Monday of each quarter and posts to Mattermost:

```
🔒 Quarterly Access Review (Q1 2026)

Active operators:
  • florin (admin) — last active: today
  • alice (operator) — last active: 45 days ago ⚠️

⚠️ alice has not accessed the platform in 45 days. Consider offboarding if no longer active.
```

Operators inactive for > 60 days are automatically flagged for review; their access is not automatically revoked (that requires explicit confirmation).

## Consequences

**Positive**
- Adding a second operator is a one-command operation rather than a manual multi-step process across six different services
- Off-boarding is complete and atomic; a compromised device or departed collaborator cannot access the platform within minutes of the offboard command being run
- `operators.yaml` provides an always-current list of who has access to what; no more "I think Alice still has SSH keys somewhere"
- The quarterly access review creates a forcing function for removing stale access before it becomes a security risk

**Negative / Trade-offs**
- Step-ca SSH certificate revocation leaves a 24-hour window for the current certificate; for emergency revocation, OCSP must be configured on step-ca (not currently enabled)
- Tailscale device removal requires Tailscale admin API access; the Tailscale API token must be stored in OpenBao and refreshed periodically
- The Mattermost welcome message includes a Tailscale invite URL; if Mattermost is down at onboarding time, the invite must be sent manually

## Alternatives Considered

- **Manual access management with a checklist**: the current state; checklists get missed; access is not revoked consistently; there is no inventory
- **Ansible playbooks for access management**: Ansible can manage Keycloak users via the `community.general.keycloak_user` module; but the onboarding/offboarding workflow needs conditional logic, error handling, and an audit trail that a Windmill workflow provides more cleanly
- **LDAP as the central identity store**: LDAP + LDAP-integrated services would make a single directory the source of truth; appropriate for large organisations; over-engineered for a homelab where Keycloak already provides the same functionality via OIDC

## Related ADRs

- ADR 0014: Tailscale private access (network access for operators)
- ADR 0042: step-ca (SSH certificate issuance and revocation)
- ADR 0043: OpenBao (secret access policies per operator role)
- ADR 0044: Windmill (onboarding/offboarding workflows run here)
- ADR 0046: Identity classes (operator identity classes are defined there)
- ADR 0056: Keycloak SSO (user and role management)
- ADR 0066: Mutation audit log (all access changes recorded here)
- ADR 0122: Windmill operator access admin surface (browser-first admin UI on top of this workflow)
