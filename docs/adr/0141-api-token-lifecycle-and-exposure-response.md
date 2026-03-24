# ADR 0141: API Token Lifecycle and Exposure Response

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The platform issues API tokens and credentials for several classes of actors:

- **Keycloak client credentials** for agent identities (`agent/triage-loop`, `agent/observation-loop`, `agent/claude-code`).
- **OpenBao API tokens** for workflow jobs that read secrets during execution.
- **Windmill API tokens** for external trigger scripts and the platform CLI.
- **Grafana service account tokens** for monitoring automation.
- **step-ca bootstrap tokens** for new service certificate provisioning.
- **Gitea personal access tokens** (if ADR 0143 is implemented) for CI automation.

These tokens are managed with varying degrees of lifecycle discipline:

- OpenBao tokens issued to Windmill jobs have a TTL tied to the job duration (short-lived, well-managed).
- Keycloak client credentials are long-lived client secrets rotated only when a rotation workflow is explicitly triggered.
- Windmill personal access tokens have no enforced TTL; an operator can create a token that never expires.
- Platform CLI tokens stored in `~/.config/lv3/token` may be indefinitely valid.

The missing element is an end-to-end token lifecycle policy that:
1. Enforces maximum TTLs for each token class.
2. Defines a canonical revocation procedure when a token is suspected to have been exposed.
3. Runs an automated audit that detects long-lived tokens approaching or exceeding their maximum TTL.
4. Defines the incident response playbook for a confirmed token exposure.

Without a defined policy, a token that appears in a log, a git diff, a Mattermost message, or a screenshot remains valid indefinitely. The exposure becomes a permanent vulnerability rather than a time-bounded one.

## Decision

We will define a **token lifecycle policy** in `config/token-policy.yaml` and implement automated enforcement and a runbook for exposure response.

### Token class policy

```yaml
# config/token-policy.yaml

token_classes:

  - class: keycloak_client_secret
    max_ttl_days: 90
    rotation_trigger: manual_or_scheduled
    storage: openbao
    revocation_workflow: rotate-keycloak-client-secret
    on_exposure: immediate_revocation

  - class: openbao_api_token
    max_ttl_days: 1         # Workflow-scoped; expires when job completes
    rotation_trigger: automatic_per_job
    storage: in_memory_only
    on_exposure: token_already_expired

  - class: windmill_api_token
    max_ttl_days: 30
    rotation_trigger: scheduled_monthly
    storage: openbao
    revocation_workflow: rotate-windmill-token
    on_exposure: immediate_revocation

  - class: grafana_service_account_token
    max_ttl_days: 90
    rotation_trigger: scheduled_quarterly
    storage: openbao
    revocation_workflow: rotate-grafana-service-token
    on_exposure: immediate_revocation

  - class: platform_cli_token
    max_ttl_days: 7         # Operator tokens expire weekly; re-authenticate via Keycloak
    rotation_trigger: automatic_at_expiry
    storage: local_keychain
    on_exposure: immediate_revocation_plus_session_invalidation

  - class: step_ca_bootstrap_token
    max_ttl_days: 1         # One-time use; expires after first certificate issuance
    rotation_trigger: automatic_on_use
    storage: openbao
    on_exposure: immediate_revocation
```

### Token inventory audit (weekly)

A weekly Windmill workflow `audit-token-inventory` queries all token-issuing systems for active tokens and validates them against the policy:

```python
for keycloak_client in keycloak.list_clients():
    secret_created_at = keycloak.get_client_secret_created_at(keycloak_client.id)
    age_days = (now() - secret_created_at).days
    if age_days > policy["keycloak_client_secret"]["max_ttl_days"]:
        findings.append({
            "token_class": "keycloak_client_secret",
            "client_id": keycloak_client.id,
            "age_days": age_days,
            "action": "rotation_required"
        })
```

Findings are posted to `#platform-security` and written to the ledger. Tokens exceeding their TTL by more than 7 days trigger an automated rotation (if a rotation workflow exists for the class) or a CRITICAL alert.

### Exposure response runbook

When a token is suspected of exposure (found in a log, git diff, Mattermost history, or external report), the operator runs:

```bash
$ lv3 runbook execute token-exposure-response --token-class keycloak_client_secret --client-id agent/triage-loop
```

The runbook automation executor (ADR 0129) drives these steps:

```yaml
# docs/runbooks/token-exposure-response.md automation block
steps:
  - id: identify-exposure-window
    type: diagnostic
    description: Query audit logs for all API calls made with the exposed token in the last 90 days
    workflow_id: query-token-audit-log
    params:
      token_class: "{{ token_class }}"
      client_id: "{{ client_id }}"

  - id: immediate-revocation
    type: mutation
    description: Revoke the exposed token and issue a replacement
    workflow_id: "{{ policy[token_class].revocation_workflow }}"
    params:
      client_id: "{{ client_id }}"
    success_condition: "result.new_token_issued == true"

  - id: session-invalidation
    type: mutation
    description: Invalidate all active sessions for this client
    workflow_id: invalidate-keycloak-sessions
    params:
      client_id: "{{ client_id }}"

  - id: impact-assessment
    type: diagnostic
    description: Determine what the exposed token could have accessed
    workflow_id: assess-token-permissions
    params:
      token_class: "{{ token_class }}"
      client_id: "{{ client_id }}"
      exposure_window_start: "{{ steps.identify-exposure-window.result.earliest_use }}"

  - id: document-incident
    type: system
    description: Create incident case in case library
    workflow_id: create-security-incident-case
    params:
      incident_type: token_exposure
      client_id: "{{ client_id }}"
      impact_summary: "{{ steps.impact-assessment.result.summary }}"
```

### Platform CLI token expiry

The platform CLI (`lv3`) must check its stored token's expiry before each command and prompt for re-authentication if within 24 hours of expiry:

```bash
$ lv3 context show
⚠ Your platform token expires in 22 hours. Run `lv3 auth login` to renew.
```

## Consequences

**Positive**

- Every token class has an explicit maximum lifetime. A token that is exposed today has a bounded worst-case validity window.
- The weekly audit ensures that forgotten tokens (a Windmill token created for a test run that was never cleaned up) are caught before they can be used as attack vectors.
- The exposure response runbook gives operators a deterministic, tested procedure rather than an ad hoc response under pressure during an incident.

**Negative / Trade-offs**

- Short-lived platform CLI tokens (7-day TTL) mean operators must re-authenticate weekly. This is minor friction but may be perceived as annoying in a homelab where the same laptop is used for years without disruption.
- The token audit requires read access to every token-issuing system (Keycloak, Windmill, Grafana). If any system's API does not support querying token creation time, that class will have incomplete audit coverage.

## Boundaries

- This ADR defines lifecycle policy and revocation procedures. It does not govern how secrets are stored at rest (that is ADR 0043: OpenBao) or how they are rotated on a schedule (ADR 0065).
- SSH certificates managed by step-ca have their own TTL and renewal cycle and are out of scope; they never exist as "tokens" in the sense used here.

## Related ADRs

- ADR 0043: OpenBao (storage for tokens subject to this policy)
- ADR 0044: Windmill (Windmill API tokens)
- ADR 0047: Short-lived credentials (philosophical alignment; this ADR adds automation)
- ADR 0056: Keycloak SSO (Keycloak client secrets)
- ADR 0065: Secret rotation automation (scheduled rotation workflows referenced here)
- ADR 0090: Platform CLI (CLI token TTL enforcement)
- ADR 0115: Event-sourced mutation ledger (token audit findings and revocation events)
- ADR 0129: Runbook automation executor (exposure response runbook driven by executor)
- ADR 0138: Published artifact secret scanning (detection feeds into exposure response)
