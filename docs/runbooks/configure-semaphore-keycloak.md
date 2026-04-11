# Configure Semaphore with Keycloak OIDC

## Purpose

Configure Semaphore to use the shared Keycloak broker for routine browser
sign-in while keeping the repo-managed `ops-semaphore` login path available for
recovery.

The dedicated Keycloak client is no longer created manually. The repo-managed
`playbooks/semaphore.yml` flow reconciles the `semaphore` client, mirrors its
secret to `.local/keycloak/semaphore-client-secret.txt`, and then converges the
Semaphore runtime with that secret.

## Desired Auth Model

- **Routine operator access**: Keycloak OIDC through the dedicated confidential
  `semaphore` client
- **Break-glass access**: repo-managed `ops-semaphore` username/password stored
  under `.local/semaphore/admin-password.txt`
- **Automation access**: repo-managed API token stored under
  `.local/semaphore/api-token.txt`

## Repo-Managed Converge Flow

### 1. Ensure Keycloak is healthy enough to reconcile clients

If the shared Keycloak admin client secret is missing locally or the Keycloak
runtime drifted, converge Keycloak first:

```bash
make converge-keycloak env=production
```

### 2. Syntax-check the Semaphore workflow

```bash
make syntax-check-semaphore
```

### 3. Converge Semaphore

```bash
make converge-semaphore env=production
```

This flow:

1. waits for the private Keycloak admin API
2. reconciles the dedicated `semaphore` OIDC client
3. mirrors the client secret to `.local/keycloak/semaphore-client-secret.txt`
4. converges the Semaphore runtime on `runtime-control`
5. refreshes the controller-local Semaphore auth artifacts under `.local/semaphore/`

### 4. Verify the login paths

```bash
SEMAPHORE_BASE_URL="$(jq -r '.base_url' .local/semaphore/admin-auth.json)"
curl -fsS "$SEMAPHORE_BASE_URL/api/ping"
curl -fsSI "$SEMAPHORE_BASE_URL/auth/oidc/login"
make semaphore-manage ACTION=list-projects
make semaphore-manage ACTION=run-template SEMAPHORE_ARGS='--template "Semaphore Self-Test" --wait'
```

Expected results:

- `/api/ping` returns a successful response from the private controller URL
- `/auth/oidc/login` returns a redirect into Keycloak
- the governed wrapper can still authenticate with the fallback admin material
- the seeded self-test template completes successfully

## Managed Artifacts

- `.local/keycloak/semaphore-client-secret.txt`
  Repo-managed mirror of the Keycloak OIDC client secret consumed by Semaphore
- `.local/semaphore/admin-password.txt`
  Repo-managed break-glass admin password
- `.local/semaphore/api-token.txt`
  Repo-managed Semaphore API token used by the governed wrapper
- `.local/semaphore/admin-auth.json`
  Controller-local auth payload that records the private controller URL plus
  the current bootstrap identity and API token

## Troubleshooting

### Missing `.local/keycloak/semaphore-client-secret.txt`

1. Verify the shared Keycloak runtime is healthy.
2. Ensure `.local/keycloak/admin-client-secret.txt` exists.
3. Re-run `make converge-semaphore env=production`.
4. If the admin client secret is missing locally, run
   `make converge-keycloak env=production` first.

### OIDC login endpoint does not redirect

1. Run `curl -fsSI "$SEMAPHORE_BASE_URL/auth/oidc/login"` and confirm a
   redirect response is returned.
2. Inspect the guest runtime:
   ```bash
   docker compose --file /opt/semaphore/docker-compose.yml logs --tail=100
   ```
3. Confirm the Keycloak client still has the controller callback URI
   registered through the repo-managed converge path.

### Secret exposure or forced rotation

1. Rotate the `semaphore` client secret in Keycloak.
2. Re-run `make converge-semaphore env=production` so the controller-local
   mirror and guest runtime both pick up the new secret.
3. Re-run the verification commands above and record the new evidence.

## Related Documentation

- [Configure Semaphore](configure-semaphore.md)
- [Configure Keycloak](configure-keycloak.md)
- ADR 0056: Keycloak as shared SSO broker
- ADR 0149: Semaphore for Ansible job management UI and API
- ADR 0361: Semaphore Keycloak OIDC integration
