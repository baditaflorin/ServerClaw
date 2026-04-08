# Semaphore Quick Start Guide - WS-0362

## 🚀 Access Semaphore Right Now

### Login Credentials (Fallback Username/Password)

```
URL:      http://100.64.0.1:8020
Username: ops-semaphore
Password: 62r4JXGau0hOjYdSLIPJL4yPNkoejC99
```

**That's it!** You can access Semaphore immediately with these credentials.

---

## 🔑 Set Up Keycloak SSO (Optional but Recommended)

### Step 1: Create Keycloak Client (5 minutes)

1. Go to Keycloak: `https://auth.lv3.org/admin`
2. Click **Clients** → **Create client**
3. Fill in:
   - **Client type**: OpenID Connect
   - **Client ID**: `semaphore`
   - **Client authentication**: Turn ON (Confidential)
4. In Login Settings:
   - **Valid redirect URIs**: `http://100.64.0.1:8020/auth/oidc/callback`
   - **Valid post logout redirect URIs**: `http://100.64.0.1:8020`
5. Go to **Credentials** tab and copy the **Client secret**

### Step 2: Create Keycloak User (2 minutes)

1. Click **Users** → **Create new user**
2. Set:
   - **Username**: `ops`
   - **Email**: `ops@lv3.org`
   - Toggle **Email verified**: ON
3. Go to **Credentials** tab, set password, toggle **Temporary**: OFF

### Step 3: Deploy Semaphore with OIDC (5 minutes)

```bash
make converge-semaphore env=production
```

---

## ✅ Verify It's Working

After the converge completes:

1. **Visit Semaphore**: `http://100.64.0.1:8020`
2. You should see:
   - **"Login with Keycloak"** button (NEW!)
   - **Username/Password** fields (fallback)
3. Click **"Login with Keycloak"**
4. Sign in with Keycloak user: `ops` / `[your password]`

---

## 📝 Configuration Files

All changes have been made to the codebase:

```
Collections/Ansible (Updated):
  roles/semaphore_runtime/defaults/main.yml      → Added OIDC variables
  roles/semaphore_runtime/templates/semaphore.env.j2  → Added OIDC env
  roles/semaphore_runtime/tasks/main.yml         → Added secret handling
  roles/semaphore_runtime/meta/argument_specs.yml → Added documentation

Documentation (Created):
  docs/runbooks/configure-semaphore-keycloak.md   → Complete setup guide
  docs/workstreams/ws-0362-semaphore-keycloak-oidc.md → Implementation notes

Credentials:
  .local/semaphore/admin-password.txt             → Admin password
  .local/semaphore/oidc-client-secret.txt         → OIDC secret
  .local/semaphore/SETUP-CREDENTIALS.txt          → Full reference
```

---

## 🔒 Security Notes

- **Credentials are generated locally** in `.local/semaphore/`
- **Passwords are 600-mode protected** (read-only for owner)
- **Fallback auth always available** if OIDC fails
- **OIDC is optional** - disable with `semaphore_enable_oidc: false`

---

## 🐛 Troubleshooting

**Q: "Login with Keycloak" button not showing?**
- Run: `docker logs semaphore | grep OIDC`
- Verify: `docker exec semaphore env | grep SEMAPHORE_OIDC`
- Re-converge: `make converge-semaphore env=production`

**Q: OIDC login fails?**
- Check Keycloak callback URL matches: `http://100.64.0.1:8020/auth/oidc/callback`
- Check user has email configured in Keycloak
- Check Tailscale proxy: `systemctl status lv3-tailscale-proxy-semaphore.socket`

**Q: Stuck on login page?**
- Use fallback credentials: `ops-semaphore` / `62r4JXGau0hOjYdSLIPJL4yPNkoejC99`
- Check browser console for JavaScript errors
- Check Semaphore logs: `docker logs -f semaphore`

---

## 📚 Full Documentation

- **Complete setup guide**: `docs/runbooks/configure-semaphore-keycloak.md`
- **Workstream details**: `docs/workstreams/ws-0362-semaphore-keycloak-oidc.md`
- **Keycloak setup**: `docs/runbooks/configure-keycloak.md`
- **Semaphore baseline**: `docs/adr/0149-semaphore-service-baseline.md`

---

## 🎯 Next Steps

1. **Right now**: Log in with fallback credentials
2. **Next 15 min**: (Optional) Set up Keycloak SSO following Step 1-3 above
3. **Commit changes**: Merge WS-0362 to main
4. **Live apply**: Run `make converge-semaphore env=production`

---

**Created**: 2026-04-06
**Workstream**: WS-0362
**Status**: Ready to deploy
