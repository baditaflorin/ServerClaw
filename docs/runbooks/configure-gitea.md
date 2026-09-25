# Configure Gitea

This runbook covers the private Gitea deployment introduced by ADR 0143.

## Purpose

`git.example.com` provides the self-hosted Git and CI surface for LV3. It runs privately on `runtime-control`, uses PostgreSQL on `postgres`, authenticates operators through Authentik, stores LFS payloads in the shared MinIO bucket `gitea-lfs`, and dispatches Actions jobs to `docker-build`.

## Managed Paths

- Runtime host: `runtime-control`
- Database host: `postgres`
- Runner host: `docker-build`
- Controller URL: `http://gitea.internal.example:3009`
- Local bootstrap artifacts: `.local/gitea/`
- Renovate bot password mirror: `.local/gitea/renovate-password.txt`
- ADR 0233 public verifier: `keys/gitea-release-bundle-cosign.pub` in the active checkout

## Converge

Before the first ADR 0233 replay, bootstrap the local signing material once:

```bash
python3 scripts/release_bundle.py init-signing
```

This writes:

- `.local/gitea/release-bundle-cosign.key`
- `.local/gitea/release-bundle-cosign.password.txt`
- `keys/gitea-release-bundle-cosign.pub` in the current checkout

Then run the managed converge so Gitea seeds the private repo Actions secrets:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/gitea.yml
```

Ensure the shared LFS secret already exists locally before replaying Gitea:

```bash
test -s .local/gitea/minio-secret-key.txt
```

The same converge now also ensures the dedicated `renovate-bot` identity exists
and has repo-scoped write access to `platform/infrastructure` for ADR 0297.

## Authentik least-privilege sign-in

Gitea accepts users carrying the Authentik `gitea-users` group claim. The
bootstrap operator has this group as well as `platform-admins`; only
`platform-admins` maps to `ops/Owners`. The `gitea-users` group alone does not
grant Authentik administration, Gitea administration, or an organization team.

The normal identity manifest reconciles the group and operator membership but
does not create any test account. To create the opt-in E2E identity, select the
intended deployment overlays first, then generate a local-only password:

```bash
LOCAL_ROOT="$(scripts/resolve_local_overlay_root.sh)"
uv run --with pyyaml python scripts/gitea_authentik_e2e.py prepare-password
```

Invoke the separate manifest explicitly. The token is read from its protected
file; never place its contents on a command line or in a receipt:

```bash
uv run --with pyyaml python scripts/reconcile_authentik_identities.py \
  --manifest config/authentik/test-identities.yaml \
  --base-url "https://id.${PLATFORM_DOMAIN}" \
  --token-file "${LOCAL_ROOT}/authentik/bootstrap-token.txt" \
  --platform-domain "${PLATFORM_DOMAIN}" \
  --platform-config-prefix "${PLATFORM_CONFIG_PREFIX}" \
  --authentik-bootstrap-admin-username "${AUTHENTIK_BOOTSTRAP_ADMIN_USERNAME}" \
  --platform-operator-name "${PLATFORM_OPERATOR_NAME}" \
  --platform-operator-email "${PLATFORM_OPERATOR_EMAIL}" \
  --apply
```

After the API reports a successful apply, run the browser flow with the private
root CA in an isolated, temporary Firefox profile. TLS verification remains
enabled, and the CA is not added to the workstation's system trust store:

```bash
uv run --with playwright python scripts/gitea_authentik_e2e.py verify \
  --platform-domain "${PLATFORM_DOMAIN}" \
  --password-file "${LOCAL_ROOT}/authentik/gitea-e2e-initial-password.txt" \
  --root-ca-file "${LOCAL_ROOT}/step-ca/certs/root_ca.crt"
```

The smoke succeeds only if Authentik returns to Gitea, Gitea's browser session
reports the expected username, and Gitea confirms `is_admin: false`. It emits
no password, token, OAuth state, authorization code, or detailed browser URL.
For interactive access in the operator's own browser, follow the internal CA
trust instructions in [configure-step-ca.md](configure-step-ca.md); never
bypass a certificate warning.

## Verify

Set the selected deployment's private endpoint and organization/repository
before running the checks. Keep those values in the local shell or ignored
deployment overlay, not in this runbook:

```bash
LOCAL_ROOT="$(scripts/resolve_local_overlay_root.sh)"
: "${GITEA_BASE_URL:?set the private Gitea base URL}"
: "${GITEA_ORG:?set the organization to verify}"
: "${GITEA_REPO:?set the repository to verify}"
```

1. Confirm the private login page responds:

```bash
curl -sf "${GITEA_BASE_URL}/user/login" >/dev/null
```

2. Confirm the mirrored admin and runner tokens exist:

```bash
test -s "${LOCAL_ROOT}/gitea/admin-token.txt"
test -s "${LOCAL_ROOT}/gitea/runner-registration-token.txt"
```

3. Confirm the ADR 0233 signing material exists locally:

```bash
test -s "${LOCAL_ROOT}/gitea/release-bundle-cosign.key"
test -s "${LOCAL_ROOT}/gitea/release-bundle-cosign.password.txt"
test -s keys/gitea-release-bundle-cosign.pub
```

4. Confirm the Renovate bot password mirror exists locally:

```bash
test -s "${LOCAL_ROOT}/gitea/renovate-password.txt"
```

5. Confirm the build worker container is running:

```bash
ansible docker-build -i inventory/hosts.yml -b -m command -a "docker ps --filter name=lv3-gitea-runner --format {{.Names}}"
```

6. Confirm the Gitea admin API sees the runner online:

```bash
GITEA_TOKEN="$(tr -d '\n' < "${LOCAL_ROOT}/gitea/admin-token.txt")"
curl -sS \
  -H "Authorization: token ${GITEA_TOKEN}" \
  "${GITEA_BASE_URL}/api/v1/admin/actions/runners" | \
  jq '{total_count, runners: [.runners[] | {name, status, busy, labels: [.labels[].name]}]}'
```

7. Confirm a branch push is accepted by the private repository gate and
produces a successful Actions run:

```bash
GITEA_TOKEN="$(tr -d '\n' < "${LOCAL_ROOT}/gitea/admin-token.txt")"
GITEA_BASIC_AUTH="$(printf '%s:%s' "${GITEA_USERNAME:?set the Gitea service username}" "${GITEA_TOKEN}" | base64)"
git -c http.extraHeader="Authorization: Basic ${GITEA_BASIC_AUTH}" \
  push "${GITEA_BASE_URL}/${GITEA_ORG}/${GITEA_REPO}.git" \
  HEAD:refs/heads/codex/gitea-runner-smoke

curl -sS \
  -H "Authorization: token ${GITEA_TOKEN}" \
  "${GITEA_BASE_URL}/api/v1/repos/${GITEA_ORG}/${GITEA_REPO}/actions/runs?limit=1" | \
  jq '{workflow_runs: [.workflow_runs[] | {id, status, conclusion, head_branch, head_sha}]}'
```

8. Confirm the runtime env now declares MinIO-backed LFS. Supply the selected
deployment's private SSH aliases and key path locally:

```bash
ssh -i "${GITEA_SSH_KEY:?set the private deployment SSH key}" \
  -o IdentitiesOnly=yes \
  -J "${GITEA_CONTROL_HOST:?set the private control-host alias}" \
  "${GITEA_RUNTIME_HOST:?set the private Gitea runtime alias}" \
  'sudo grep -E "^GITEA__lfs__" /run/lv3-secrets/gitea/runtime.env'
```

## Smoke-Test Repository Creation

Use the mirrored admin token to create a private smoke-test repository under
the selected managed organization:

```bash
GITEA_TOKEN="$(tr -d '\n' < "${LOCAL_ROOT}/gitea/admin-token.txt")"
curl -sS \
  -H "Authorization: token ${GITEA_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"name":"ci-webhook-smoke","private":true,"auto_init":false}' \
  "${GITEA_BASE_URL}/api/v1/orgs/${GITEA_ORG}/repos"
```

## Managed Hook Path

The repo-managed validation hook template lives at:

- `/opt/gitea/pre-receive.validation-hook`

For a repository, the canonical hook is installed under its Gitea data
directory at:

- `/opt/gitea/data/git/repositories/<organization>/<repository>.git/custom_hooks/pre-receive`

## Notes

- Gitea is private-only. Do not add a public edge publication for it.
- The bootstrap admin and runner registration tokens are mirrored locally for controlled operator workflows; keep `.local/gitea/` outside commits.
- ADR 0233 also seeds the private repo Actions secret `RELEASE_BUNDLE_REPO_TOKEN` from the mirrored Gitea admin token so server-resident workflows can publish and re-download private release assets during verification.
- ADR 0297 reuses the same bootstrap path to keep the dedicated `renovate-bot`
  account present and mirrored locally, while the workflow itself mints a
  short-lived scoped token at runtime instead of reusing a durable PAT.
- The private git push path enforces the server-side validation gate before a ref is accepted. A rejected push can fail before any Actions workflow is created.
- The Gitea SSH endpoint uses Gitea account keys, not the infrastructure bootstrap key. For controlled automation, use the deployment's documented credential path rather than reusing a host key.
- ADR 0233 reuses the managed Gitea bootstrap path to seed the private repo Actions secrets `RELEASE_BUNDLE_COSIGN_PRIVATE_KEY`, `RELEASE_BUNDLE_COSIGN_PASSWORD`, and `RELEASE_BUNDLE_REPO_TOKEN`.
- ADR 0274 replaces local-disk LFS storage with the shared MinIO bucket `gitea-lfs`; do not manage LFS objects directly on the docker-runtime filesystem.
- The Renovate-specific workflow path is documented in [configure-renovate.md](configure-renovate.md).
- The signed bundle build, publish, and verification flow is documented in [signed-release-bundles.md](signed-release-bundles.md).
