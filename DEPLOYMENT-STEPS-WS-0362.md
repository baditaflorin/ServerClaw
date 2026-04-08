# WS-0362 Full Deployment Steps

## Status
✅ Code committed: `147cf950e`
⏳ Ready to deploy
❌ Not yet applied to runtime

## What's Committed

```
[ws-0362] Add Keycloak OIDC SSO to Semaphore — full deployment
- semaphore_runtime role with OIDC support
- ADR 0361: Architecture decision
- Full documentation and guides
```

## Step 1: Sync Code to Platform

Push changes to main (or intermediate branch):

```bash
# From worktree root
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.claude/worktrees/stoic-kalam

# Push to origin
git push origin claude/stoic-kalam

# OR merge to main
git checkout main
git merge claude/stoic-kalam
git push origin main
```

## Step 2: Pull Latest on Control Machine

On the controller (runtime-control-lv3 or wherever you run playbooks):

```bash
cd /path/to/proxmox_florin_server

# Pull latest code
git pull origin main

# Verify WS-0362 changes are present
git log --oneline | grep "ws-0362" | head -1
```

## Step 3: Run Semaphore Converge

From the platform's control machine:

```bash
# From repo root
cd /path/to/proxmox_florin_server

# Syntax check
make syntax-check-semaphore

# Preflight
make preflight WORKFLOW=converge-semaphore

# Deploy (this applies all WS-0362 changes)
make converge-semaphore env=production
```

This will:
✅ Apply all OIDC configuration
✅ Set admin password to: `62r4JXGau0hOjYdSLIPJL4yPNkoejC99`
✅ Generate OIDC client secret
✅ Update Semaphore environment
✅ Restart Semaphore container with new config

## Step 4: Verify Semaphore is Running

After converge completes:

```bash
# Check container status
docker ps | grep semaphore

# Check logs
docker logs semaphore | tail -50

# Verify OIDC environment variables
docker exec semaphore env | grep SEMAPHORE_OIDC
```

Expected output:
```
SEMAPHORE_OIDC_PROVIDER=keycloak
SEMAPHORE_OIDC_ISSUER_URL=https://auth.lv3.org/realms/lv3
SEMAPHORE_OIDC_CLIENT_ID=semaphore
SEMAPHORE_OIDC_CALLBACK_URL=http://100.64.0.1:8020/auth/oidc/callback
SEMAPHORE_OIDC_AUTO_PROVISION_USER=true
```

## Step 5: Test Fallback Login

Access Semaphore at: `http://100.64.0.1:8020`

Login with fallback credentials:
- Username: `ops-semaphore`
- Password: `62r4JXGau0hOjYdSLIPJL4yPNkoejC99`

You should see login page with:
- Username/Password fields (working now)
- ⚠️ "Login with Keycloak" button (not yet working - needs Step 6)

## Step 6: Create Keycloak Client (Optional - for full OIDC)

Only do this if you have access to Keycloak and want to enable OIDC login.

### Via Keycloak Web Console

1. Access Keycloak: `https://auth.lv3.org/admin`
   - Or use Tailscale IP if DNS fails

2. **Create Client**:
   - Click **Clients** (left menu)
   - Click **Create client**
   - Set **Client ID**: `semaphore`
   - Set **Client type**: OpenID Connect
   - Click **Next**

3. **Capability Config**:
   - Toggle **Client authentication**: ON
   - Click **Next**

4. **Login Settings**:
   - **Valid redirect URIs**: Add `http://100.64.0.1:8020/auth/oidc/callback`
   - **Valid post logout redirect URIs**: Add `http://100.64.0.1:8020`
   - Click **Save**

5. **Get Client Secret**:
   - Go to **Credentials** tab
   - Copy the **Client secret** value
   - Store it (you'll need it for Semaphore role configuration)

### Via Keycloak API (Advanced)

```bash
# Get admin token
ADMIN_TOKEN=$(curl -s -X POST https://auth.lv3.org/realms/master/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=admin-cli&username=admin&password=$(cat .local/keycloak/admin-password.txt)&grant_type=password" \
  | jq -r '.access_token')

# Create client
curl -X POST https://auth.lv3.org/admin/realms/lv3/clients \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "clientId": "semaphore",
    "name": "Semaphore",
    "description": "Semaphore Ansible Automation",
    "enabled": true,
    "clientAuthenticatorType": "client-secret",
    "redirectUris": [
      "http://100.64.0.1:8020/auth/oidc/callback"
    ],
    "webOrigins": [
      "http://100.64.0.1:8020"
    ],
    "publicClient": false
  }'
```

## Step 7: Create Keycloak Test User

### Via Keycloak Web Console

1. Click **Users** (left menu)
2. Click **Create new user**
3. Set:
   - **Username**: `ops`
   - **Email**: `ops@lv3.org`
   - Toggle **Email verified**: ON
4. Click **Create**
5. Go to **Credentials** tab
6. Click **Set password**
7. Set your desired password
8. Toggle **Temporary**: OFF
9. Click **Set Password**

### Via Keycloak API (Advanced)

```bash
# Create user
curl -X POST https://auth.lv3.org/admin/realms/lv3/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "ops",
    "email": "ops@lv3.org",
    "enabled": true,
    "emailVerified": true,
    "firstName": "Operations",
    "lastName": "User"
  }'

# Set password
USER_ID=$(curl -s -X GET "https://auth.lv3.org/admin/realms/lv3/users?username=ops" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq -r '.[0].id')

curl -X PUT https://auth.lv3.org/admin/realms/lv3/users/$USER_ID/reset-password \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"password","value":"YourPassword123!","temporary":false}'
```

## Step 8: Verify OIDC is Working

1. **Access Semaphore**: `http://100.64.0.1:8020`
2. You should now see:
   - ✅ Username/Password login (working)
   - ✅ **"Login with Keycloak"** button (NEW!)
3. Click **"Login with Keycloak"**
4. You'll be redirected to Keycloak
5. Login with the test user created in Step 7
6. Accept consent (if prompted)
7. You'll be auto-provisioned in Semaphore and logged in

## Troubleshooting

### Issue: "Login with Keycloak" button not showing

**Cause**: OIDC environment variables not set
**Fix**:
```bash
# Re-run converge
make converge-semaphore env=production

# Or verify manually
docker exec semaphore env | grep SEMAPHORE_OIDC
```

### Issue: OIDC redirect fails

**Cause**: Invalid callback URL in Keycloak
**Fix**:
1. Check Keycloak client has exact URL: `http://100.64.0.1:8020/auth/oidc/callback`
2. Check Tailscale proxy is running: `systemctl status lv3-tailscale-proxy-semaphore.socket`

### Issue: User can't login with Keycloak

**Cause**: Missing email in Keycloak user
**Fix**:
1. Ensure Keycloak user has email set
2. Check OIDC scopes include `email`: `SEMAPHORE_OIDC_SCOPES=openid profile email`

### Issue: "Incorrect login or password"

**Cause**: Fallback auth failing - check credentials
**Fix**:
```bash
# Get correct admin password from running container
docker exec semaphore cat /etc/lv3/semaphore/admin-password
```

## Rollback (if needed)

If issues arise, you can disable OIDC:

```bash
# Edit inventory to disable OIDC
semaphore_enable_oidc: false

# Re-converge
make converge-semaphore env=production

# Login with fallback: ops-semaphore / password
```

## Summary

After all steps:
- ✅ Semaphore deployed with OIDC support
- ✅ Fallback username/password login working
- ✅ Keycloak client created
- ✅ Test user created in Keycloak
- ✅ OIDC "Login with Keycloak" button visible
- ✅ Users can SSO via Keycloak

## Documentation References

- **Setup Guide**: `docs/runbooks/configure-semaphore-keycloak.md`
- **Quick Start**: `SEMAPHORE-SETUP-QUICK-START.md`
- **Architecture**: `docs/adr/0361-semaphore-keycloak-oidc-integration.md`
- **Workstream**: `docs/workstreams/ws-0362-semaphore-keycloak-oidc.md`

## Next Steps

1. Push code to main
2. SSH into control machine
3. Run steps 2-3 (Pull + Converge)
4. Verify Step 4
5. Test Step 5
6. If you have Keycloak: Do steps 6-8
7. You're done! 🎉
