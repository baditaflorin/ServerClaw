# Runbook: Rename the live Keycloak realm `0mpc` → `0mcp`

**Status:** Ready to execute (requires a maintenance window — platform-wide SSO downtime).
**Owner:** Platform operator.
**Related:** ADR 0488 (single deployment), the `0mpc.com → 0mcp.com` domain migration (release 0.179.48).

---

## 1. Why this is needed

The domain was renamed `0mpc.com → 0mcp.com`. The platform derives the Keycloak
realm name from the domain:

```yaml
# inventory/group_vars/all/identity.yml
keycloak_realm_name: "{{ platform_domain | split('.') | first }}"   # now "0mcp"
keycloak_oidc_issuer_url: "https://sso.{{ platform_domain }}/realms/{{ keycloak_realm_name }}"
```

So **config now expects realm `0mcp`**, but the **live realm is still `0mpc`**:

```
GET https://sso.0mcp.com/realms/0mpc/.well-known/openid-configuration   → 200
GET https://sso.0mcp.com/realms/0mcp/.well-known/openid-configuration   → 404
```

Every oauth2-proxy / OIDC client issuer URL is templated from
`keycloak_realm_name`, so until the live realm matches `0mcp`, the next edge /
keycloak converge will point services at a realm that does not exist.

## 2. ⚠️ Why you cannot "just converge"

`roles/keycloak_runtime/tasks/main.yml` uses:

```yaml
- name: Ensure platform identity realm exists with hardened defaults
  community.general.keycloak_realm:
    realm: "{{ keycloak_realm_name }}"   # 0mcp
    id:    "{{ keycloak_realm_name }}"   # 0mcp
```

Running `make converge-keycloak` **without renaming first** would **create a new,
empty `0mcp` realm** and leave the populated `0mpc` realm orphaned — losing every
user, client, group, role mapping, and service account. **Do the live rename
first, then converge.**

Keycloak nuance: a realm's internal `id` is immutable. The PUT-rename below
changes the realm *name* (the segment used in all `/realms/<name>/...` URLs)
while the `id` stays `0mpc`. The role sets `id: 0mcp`, which will not match the
renamed realm's id `0mpc`. **Decision point — pick ONE in step 5.**

## 3. Pre-flight

```bash
# Confirm live state
curl -s -o /dev/null -w 'realm 0mpc: %{http_code}\n' https://sso.0mcp.com/realms/0mpc/.well-known/openid-configuration
curl -s -o /dev/null -w 'realm 0mcp: %{http_code}\n' https://sso.0mcp.com/realms/0mcp/.well-known/openid-configuration
# Expect: 0mpc 200, 0mcp 404

# Admin creds live in .local (do NOT print them into shared logs)
#   keycloak_admin_username / keycloak_admin_password — see .local/keycloak/ or identity overlay
KC=https://sso.0mcp.com
```

Get an admin token (master realm):

```bash
TOKEN=$(curl -s "$KC/realms/master/protocol/openid-connect/token" \
  -d grant_type=password -d client_id=admin-cli \
  -d username="$KC_ADMIN_USER" -d password="$KC_ADMIN_PASS" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

## 4. Back up the realm (mandatory)

```bash
# Full partial-export of the realm incl. clients, roles, groups, and users.
curl -s -X POST "$KC/admin/realms/0mpc/partial-export?exportClients=true&exportGroupsAndRoles=true" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  > ~/keycloak-0mpc-backup-$(date +%Y%m%d).json
# Users are NOT included in partial-export; if you need a users backup, use
# kc.sh export on the Keycloak host, or accept that users persist through the
# in-place rename (they do — rename does not touch user records).
wc -c ~/keycloak-0mpc-backup-*.json   # sanity: non-trivial size
```

## 5. Open a maintenance window, then rename

Announce SSO downtime. All oauth2-proxy-fronted subdomains (grafana, ops-portal,
adminer, etc.) will reject logins until step 6 completes.

**Option A — in-place rename (preserves everything; realm id stays `0mpc`):**

```bash
curl -s -X PUT "$KC/admin/realms/0mpc" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"realm":"0mcp"}'
# Verify
curl -s -o /dev/null -w 'realm 0mcp: %{http_code}\n' "$KC/realms/0mcp/.well-known/openid-configuration"  # expect 200
```

Then make the role idempotent against the renamed realm whose id is still `0mpc`.
**Pin the id** so the `keycloak_realm` task updates (not recreates) it:

```yaml
# inventory/group_vars/all/identity.yml  (add, alongside keycloak_realm_name)
keycloak_realm_id: "0mpc"   # immutable internal id; realm NAME is 0mcp
```
…and change `roles/keycloak_runtime/tasks/main.yml` `id:` to
`"{{ keycloak_realm_id | default(keycloak_realm_name) }}"`. (Small, separate PR.)

**Option B — fresh realm via import (clean id `0mcp`, more steps):**

```bash
# Edit the backup: set "realm":"0mcp" and "id":"0mcp", then import.
sed -i '' 's/"realm" *: *"0mpc"/"realm":"0mcp"/; s/"id" *: *"0mpc"/"id":"0mcp"/' ~/keycloak-0mpc-backup-*.json
curl -s -X POST "$KC/admin/realms" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d @~/keycloak-0mpc-backup-*.json
# Users are not in the partial export — re-create or migrate separately.
# Once verified, delete the old realm:  DELETE $KC/admin/realms/0mpc
```

> Recommendation: **Option A** unless you specifically need the internal id to be
> `0mcp`. It is the true "rename", preserves users without a separate migration,
> and is reversible (PUT `{"realm":"0mpc"}` to roll back).

## 6. Reconcile config → live (re-converge)

```bash
# Pre-converge .env workaround (per CLAUDE.md)
mv .local/open-webui/provider.env{,.bak} 2>/dev/null || true
mv .local/serverclaw/provider.env{,.bak} 2>/dev/null || true

make converge-keycloak env=production
make configure-edge-publication env=production   # re-render oauth2-proxy issuer/login/token/jwks URLs

# Restore
mv .local/open-webui/provider.env{.bak,} 2>/dev/null || true
mv .local/serverclaw/provider.env{.bak,} 2>/dev/null || true
```

## 7. Verify

```bash
curl -s -o /dev/null -w 'realm 0mcp: %{http_code}\n' https://sso.0mcp.com/realms/0mcp/.well-known/openid-configuration   # 200
curl -s -o /dev/null -w 'realm 0mpc: %{http_code}\n' https://sso.0mcp.com/realms/0mpc/.well-known/openid-configuration   # 404 (A) / 200-until-deleted (B)
# Log into one SSO-fronted app end-to-end (e.g. grafana.0mcp.com) and confirm token issuance.
```

## 8. Rollback

- **Option A:** `PUT $KC/admin/realms/0mcp -d '{"realm":"0mpc"}'`, revert the
  `keycloak_realm_id` config change, re-converge.
- **Option B:** re-point config to `0mpc`, delete the half-built `0mcp` realm.

## 9. Close-out

- Live-apply receipt + `platform_version` bump per CLAUDE.md §5.
- Note the rename in the changelog under the next release.
