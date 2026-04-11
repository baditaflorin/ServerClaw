# Operator Offboarding Checklist Template

Use this when a temporary account expires or an operator leaves.

---

## Operator Details

| Field | Value |
|-------|-------|
| **Operator ID** | |
| **Username** | |
| **Email** | |
| **Expiry Date** | |
| **Offboarded By** | |
| **Offboarded At** | |

---

## Offboarding Steps

### 1. Keycloak — Disable Account
- [ ] Log in to https://sso.example.com/admin/master/console/#/lv3/users
- [ ] Find user by username
- [ ] Set `Enabled` = OFF
- [ ] Terminate all active sessions

Or via API:
```bash
# Get token
TOKEN=$(curl -sk https://sso.example.com/realms/master/protocol/openid-connect/token \
  -d "client_id=admin-cli&grant_type=password&username=lv3-bootstrap-admin&password=$(cat .local/keycloak/bootstrap-admin-password.txt)" \
  | jq -r .access_token)

# Get user ID
USER_ID=$(curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://sso.example.com/admin/realms/lv3/users?username=<USERNAME>&exact=true" \
  | jq -r '.[0].id')

# Disable user
curl -sk -X PUT -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://sso.example.com/admin/realms/lv3/users/$USER_ID" \
  -d '{"enabled": false}'
```

### 2. Headscale — Revoke VPN Access
- [ ] Remove pre-auth key: `rm .local/headscale/<username>-authkey.txt`
- [ ] Expire nodes (optional — they'll expire naturally):
  ```bash
  headscale nodes list --user <username>
  headscale nodes expire --identifier <node-id>
  ```

### 3. Operator Roster — Update Status
- [ ] Edit `config/operators.yaml`:
  ```yaml
  - id: <operator-id>
    status: inactive    # was: active
    keycloak:
      enabled: false    # was: true
  ```

### 4. Clean Up Local Secrets
- [ ] Archive (don't delete) password file:
  ```bash
  mv .local/keycloak/<username>-password.txt \
     .local/keycloak/<username>-password.txt.revoked
  ```

### 5. Commit and Push
```bash
git add config/operators.yaml
git commit -m "[offboard] Disable <operator-id> — account expired"
git push origin main
```

### 6. Notify
- [ ] Notify the operator that access has been revoked
- [ ] Update any shared docs/runbooks referencing this operator
