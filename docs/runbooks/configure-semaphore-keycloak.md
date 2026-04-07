# Configure Semaphore with Keycloak OIDC

## Purpose

Configure Semaphore to support Keycloak SSO authentication while maintaining fallback username/password login.

## Prerequisites

- Keycloak is deployed and accessible at `https://auth.lv3.org`
- Semaphore database and runtime are deployed
- Administrator access to Keycloak admin console

## Setup Steps

### 1. Create Keycloak Client for Semaphore

1. Log into Keycloak admin console: `https://auth.lv3.org/admin`
2. Navigate to **Clients** in the left sidebar
3. Click **Create client**
4. Set the following values:
   - **Client type**: OpenID Connect
   - **Client ID**: `semaphore`
   - Click **Next**

5. On the Capability config page:
   - **Client authentication**: Toggle ON (confidential client)
   - **Authorization**: Toggle OFF
   - Click **Next**

6. On the Login settings page:
   - **Valid redirect URIs**: Add `http://100.64.0.1:8020/auth/oidc/callback`
   - **Valid post logout redirect URIs**: Add `http://100.64.0.1:8020`
   - Click **Save**

### 2. Retrieve Client Secret

1. Go to the **semaphore** client credentials tab
2. Copy the **Client secret** value
3. Store it securely - you'll need this for Semaphore configuration

### 3. Configure User for Keycloak Login

In Keycloak, create or verify a user account:

1. Navigate to **Users**
2. Click **Create new user**
3. Set **Username**: `ops` (or desired username)
4. Set **Email**: `ops@lv3.org` (or desired email)
5. Toggle **Email verified**: ON
6. Click **Create**
7. Go to the **Credentials** tab
8. Set a temporary password and toggle **Temporary**: OFF

### 4. Update Semaphore Configuration

The role defaults now include Keycloak OIDC support. Update the following in your inventory if needed:

```yaml
# Enable OIDC
semaphore_enable_oidc: true

# Keycloak configuration
semaphore_oidc_provider: keycloak
semaphore_oidc_client_id: semaphore
semaphore_oidc_issuer_url: "https://auth.lv3.org/realms/lv3"
semaphore_oidc_callback_url: "http://100.64.0.1:8020/auth/oidc/callback"
semaphore_oidc_scopes: "openid profile email"
semaphore_oidc_auto_provision_user: true

# Fallback username/password auth
semaphore_admin_username: ops-semaphore
semaphore_admin_email: ops-semaphore@lv3.org
```

### 5. Deploy Semaphore with Keycloak

Run the Semaphore converge playbook to apply the OIDC configuration:

```bash
make converge-semaphore env=production
```

### 6. Verify Configuration

1. Access Semaphore at `http://100.64.0.1:8020`
2. You should now see:
   - **"Login with Keycloak"** button (OIDC)
   - **Username/Password** login fields (fallback)

## Credentials

### Keycloak Admin
- **Username**: admin
- **Password**: Stored in `.local/keycloak/admin-password.txt`

### Semaphore Admin (Fallback)
- **Username**: `ops-semaphore`
- **Password**: Generated and stored in `.local/semaphore/admin-password.txt`

### Keycloak User for SSO
- **Username**: `ops` (or as configured)
- **Password**: Set during user creation in Keycloak

## Troubleshooting

### OIDC button not appearing

1. Verify `SEMAPHORE_OIDC_PROVIDER` environment variable is set
2. Check Keycloak is reachable from Semaphore container:
   ```bash
   docker exec semaphore curl -v https://auth.lv3.org/.well-known/openid-configuration
   ```
3. Review Semaphore container logs: `docker logs semaphore`

### Invalid redirect URI error

1. Verify callback URL in Keycloak matches `semaphore_oidc_callback_url`
2. Ensure URL uses correct hostname (`100.64.0.1` for internal access)
3. Check Tailscale proxy is running: `systemctl status lv3-tailscale-proxy-semaphore.socket`

### User not auto-provisioning

1. Verify `SEMAPHORE_OIDC_AUTO_PROVISION_USER=true` in environment
2. Check user has email configured in Keycloak
3. Verify email mapping in scopes (default: `openid profile email`)

## Related Documentation

- ADR 0056: Keycloak as shared SSO broker
- Keycloak configuration runbook
- Semaphore official OIDC documentation
