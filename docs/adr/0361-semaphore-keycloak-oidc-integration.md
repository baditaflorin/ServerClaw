# ADR 0361: Semaphore Keycloak OIDC Integration

**Status**: Proposed
**Date**: 2026-04-07
**Deciders**: Platform Engineering
**Supersedes**: ADR 0149 (Semaphore baseline - enhanced with SSO)

## Context

Semaphore is deployed as the Ansible automation controller but currently relies on local username/password authentication. This creates several issues:

1. **No SSO integration** - Cannot leverage shared Keycloak identity broker (ADR 0056)
2. **Manual user management** - Each user requires manual account creation
3. **Inconsistent auth model** - Other services (Grafana, Outline, etc.) use Keycloak but Semaphore doesn't
4. **No audit trail** - User activity in Semaphore isn't connected to platform identity events

## Decision

Extend Semaphore runtime configuration to support **Keycloak OpenID Connect (OIDC)** authentication while maintaining fallback username/password login for recovery scenarios.

### Changes Made

**Role**: `semaphore_runtime`

1. **Defaults** (`defaults/main.yml`)
   - `semaphore_enable_oidc`: Toggle OIDC support (default: true)
   - `semaphore_oidc_provider`: Provider type (keycloak)
   - `semaphore_oidc_client_id`: Keycloak client ID
   - `semaphore_oidc_client_secret_*`: Secret file paths
   - `semaphore_oidc_issuer_url`: Keycloak realm endpoint
   - `semaphore_oidc_callback_url`: OAuth redirect URI
   - `semaphore_oidc_scopes`: OpenID Connect scopes
   - `semaphore_oidc_auto_provision_user`: Auto-create users on first login

2. **Environment Template** (`templates/semaphore.env.j2`)
   - Conditional OIDC environment variables passed to container
   - Variables only included when `semaphore_enable_oidc=true`

3. **Tasks** (`tasks/main.yml`)
   - Generate OIDC client secret (local + guest)
   - Persist secret in OpenBao for secret management
   - Include secret in Semaphore environment injection

4. **Documentation** (`meta/argument_specs.yml`)
   - Document all new OIDC variables and their purposes

## Rationale

### Why Keycloak OIDC?

- **Consistent identity**: Unifies authentication across all platform services (ADR 0056)
- **Better UX**: Single sign-on for operators across Grafana, Outline, Semaphore, etc.
- **Audit trail**: Centralized identity events for compliance and security
- **User auto-provisioning**: New Keycloak users automatically gain Semaphore access
- **No password reuse risk**: Users don't reuse passwords across services

### Why Keep Fallback Auth?

- **Recovery**: If Keycloak is down, admins can still access Semaphore
- **Gradual rollout**: Allows testing OIDC without removing password auth
- **Compatibility**: Existing automation/API scripts using passwords still work

### Why Optional?

- `semaphore_enable_oidc: true` by default but easily disabled
- Allows environments without Keycloak to run Semaphore
- Backward compatible with prior deployments

## Implementation

### Configuration

```yaml
# Enable OIDC (default)
semaphore_enable_oidc: true
semaphore_oidc_provider: keycloak
semaphore_oidc_client_id: semaphore
semaphore_oidc_issuer_url: "https://auth.example.com/realms/lv3"
semaphore_oidc_callback_url: "http://100.64.0.1:8020/auth/oidc/callback"
semaphore_oidc_scopes: "openid profile email"
semaphore_oidc_auto_provision_user: true

# Fallback username/password (always available)
semaphore_admin_username: ops-semaphore
```

### Secret Management

OIDC client secret is:
1. Generated locally on control machine (if missing)
2. Persisted on guest VM
3. Injected via OpenBao agent into Semaphore container
4. Never stored in plain text on disk

### Login Flow

**With OIDC Enabled:**
```
User → Semaphore Login Page
       ├─ "Login with Keycloak" (OIDC)
       └─ Username/Password (Fallback)

If OIDC selected:
User → Keycloak Login → Consent → Semaphore Auto-Provisioned

If Fallback selected:
User → ops-semaphore / password → Login
```

## Consequences

### Positive

✅ **Unified identity**: Same credentials across Grafana, Outline, Semaphore
✅ **Better security**: No password reuse, no password storage in Semaphore
✅ **Audit trail**: All logins go through Keycloak (ADR 0056 audit)
✅ **User management**: Keycloak admins control Semaphore access
✅ **Graceful degradation**: Fallback auth if Keycloak is down
✅ **Easy rollout**: Optional, backward compatible, can be disabled

### Negative

⚠️ **Keycloak dependency**: OIDC unavailable if Keycloak is unreachable
⚠️ **Configuration complexity**: More environment variables
⚠️ **Extra setup step**: Keycloak client must be created first

## Deployment

### Prerequisites

- Keycloak realm deployed (ADR 0056)
- Keycloak client created with:
  - Client type: Confidential OpenID Connect
  - Redirect URI: `http://100.64.0.1:8020/auth/oidc/callback`
  - Scopes: `openid profile email`

### Deployment Steps

1. **Create Keycloak Client** (5 min)
   ```
   Admin Console → Clients → Create
   - Client ID: semaphore
   - Type: OpenID Connect (Confidential)
   - Redirect: http://100.64.0.1:8020/auth/oidc/callback
   ```

2. **Get Client Secret** (1 min)
   ```
   Credentials Tab → Copy Client secret
   Store in: .local/semaphore/oidc-client-secret.txt
   ```

3. **Create Test User** (2 min)
   ```
   Users → Create User
   - Username: ops
   - Email: ops@example.com
   - Password: [set in credentials tab]
   ```

4. **Deploy Semaphore** (5 min)
   ```bash
   make converge-semaphore env=production
   ```

5. **Verify** (2 min)
   ```
   http://100.64.0.1:8020
   Should show "Login with Keycloak" button
   ```

## Testing Checklist

- [ ] Fallback login works (ops-semaphore + password)
- [ ] OIDC "Login with Keycloak" button visible
- [ ] Keycloak login redirects correctly
- [ ] New Keycloak users auto-provisioned
- [ ] Email claim properly mapped
- [ ] API tokens still work
- [ ] Logout flow works
- [ ] Session timeout works

## Related ADRs

- **ADR 0056**: Keycloak as shared SSO broker
- **ADR 0149**: Semaphore service baseline
- **ADR 0343**: Load auth contract compliance for operator tools

## Documentation

- **Setup Guide**: `docs/runbooks/configure-semaphore-keycloak.md`
- **Quick Start**: `SEMAPHORE-SETUP-QUICK-START.md`
- **Workstream**: `docs/workstreams/ws-0362-semaphore-keycloak-oidc.md`

## Questions

**Q: Can we use internal Keycloak URL?**
A: Yes, use internal IP if external DNS fails: `https://10.10.10.92:8080`

**Q: What if Keycloak is down?**
A: Fallback to `ops-semaphore` username/password login

**Q: Can we disable OIDC?**
A: Yes, set `semaphore_enable_oidc: false` and re-converge

**Q: Do existing scripts break?**
A: No, API tokens and username/password auth still work
