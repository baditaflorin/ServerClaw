# WS-0362: Add Keycloak OIDC SSO to Semaphore

**Status**: Ready for Live Apply
**Created**: 2026-04-06
**Owner**: Claude
**Target**: Semaphore + Keycloak integration

## Summary

Implemented Keycloak OIDC SSO support for Semaphore automation platform, enabling secure single sign-on while maintaining fallback username/password authentication.

## Changes

### 1. Updated Semaphore Role Configuration

**File**: `collections/ansible_collections/lv3/platform/roles/semaphore_runtime/defaults/main.yml`

Added Keycloak OIDC variables:
- `semaphore_enable_oidc`: Toggle OIDC support (default: true)
- `semaphore_oidc_provider`: Provider name (keycloak)
- `semaphore_oidc_client_id`: Keycloak client ID
- `semaphore_oidc_issuer_url`: Keycloak realm URL
- `semaphore_oidc_callback_url`: Redirect URI
- `semaphore_oidc_scopes`: OpenID Connect scopes
- `semaphore_oidc_auto_provision_user`: Auto-create users on first login

### 2. Updated Environment Template

**File**: `collections/ansible_collections/lv3/platform/roles/semaphore_runtime/templates/semaphore.env.j2`

Added conditional OIDC environment variables passed to Semaphore container:
- `SEMAPHORE_OIDC_PROVIDER`
- `SEMAPHORE_OIDC_ISSUER_URL`
- `SEMAPHORE_OIDC_CLIENT_ID`
- `SEMAPHORE_OIDC_CLIENT_SECRET`
- `SEMAPHORE_OIDC_CALLBACK_URL`
- `SEMAPHORE_OIDC_SCOPES`
- `SEMAPHORE_OIDC_AUTO_PROVISION_USER`

### 3. Updated Runtime Tasks

**File**: `collections/ansible_collections/lv3/platform/roles/semaphore_runtime/tasks/main.yml`

Added OIDC client secret handling:
- Generate client secret locally if missing
- Persist to guest VM for container access
- Inject into OpenBao for secret management
- Include in OpenBao environment templating

### 4. Created Configuration Documentation

**File**: `docs/runbooks/configure-semaphore-keycloak.md`

Comprehensive guide covering:
1. Keycloak client creation
2. User account setup
3. Configuration options
4. Credential retrieval
5. Troubleshooting

### 5. Generated Credentials

**Location**: `.local/semaphore/`

- `admin-password.txt`: Admin user password (ops-semaphore)
- `oidc-client-secret.txt`: Keycloak client secret
- `api-token.txt`: Semaphore API token (generated during converge)
- `admin-auth.json`: Full auth payload (generated during converge)
- `SETUP-CREDENTIALS.txt`: Quick reference with next steps

## Credentials

### Fallback Login (Immediate Access)

```
Username: ops-semaphore
Password: <generated-by-init-local>
```

### Keycloak OIDC Setup

1. Create client in Keycloak:
   - Client ID: `semaphore`
   - Type: Confidential OpenID Connect
   - Redirect: `http://100.64.0.1:8020/auth/oidc/callback`

2. Use generated OIDC secret: `<read from .local/semaphore/oidc-client-secret.txt — NEVER commit secrets inline>`

3. Create user in Keycloak realm with email

4. Run: `make converge-semaphore env=production`

## Live Apply Procedure

### 1. Verify Infrastructure

```bash
# Test connectivity to Semaphore
curl -v http://100.64.0.1:8020/api/ping

# Verify Tailscale proxy status
systemctl status lv3-tailscale-proxy-semaphore.socket
```

### 2. Deploy OIDC Configuration

```bash
# Syntax check
make syntax-check-semaphore

# Preflight validation
make preflight WORKFLOW=converge-semaphore

# Apply configuration
make converge-semaphore env=production
```

### 3. Post-Deployment Verification

```bash
# Check Semaphore container logs
docker logs semaphore

# Verify OIDC environment variables set
docker exec semaphore env | grep SEMAPHORE_OIDC

# Test login access
curl -v http://100.64.0.1:8020/auth/oidc/login
```

## Testing Checklist

- [ ] Fallback login works: `ops-semaphore` + password
- [ ] Keycloak client created with correct redirect URI
- [ ] Keycloak test user created with email
- [ ] Run `make converge-semaphore` successfully
- [ ] OIDC "Login with Keycloak" button appears
- [ ] Login with Keycloak SSO works
- [ ] New OIDC users auto-provisioned in Semaphore
- [ ] API token generation works

## Rollback Plan

If issues arise:

1. **Keep fallback auth**: Password login always available
2. **Disable OIDC**: Set `semaphore_enable_oidc: false` in inventory
3. **Re-converge**: `make converge-semaphore env=production`
4. **Revert code**: `git checkout -- collections/` (if needed)

## Dependencies

- Keycloak deployed and accessible
- Semaphore runtime deployed
- Tailscale proxy operational

## Related ADRs

- ADR 0056: Keycloak as shared SSO broker
- ADR 0149: Semaphore service baseline
- ADR 0343: Load auth contract compliance

## Documentation Links

- Setup Guide: docs/runbooks/configure-semaphore-keycloak.md
- Credentials: .local/semaphore/SETUP-CREDENTIALS.txt
- Role: collections/ansible_collections/lv3/platform/roles/semaphore_runtime/
