# Configure Gitea

This runbook covers the private Gitea deployment introduced by ADR 0143.

## Purpose

`git.lv3.org` provides the self-hosted Git and CI surface for LV3. It runs privately on `docker-runtime-lv3`, uses PostgreSQL on `postgres-lv3`, authenticates operators through Keycloak, and dispatches Actions jobs to `docker-build-lv3`.

## Managed Paths

- Runtime host: `docker-runtime-lv3`
- Database host: `postgres-lv3`
- Runner host: `docker-build-lv3`
- Controller URL: `http://100.64.0.1:3009`
- Local bootstrap artifacts: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/`
- ADR 0233 public verifier: `keys/gitea-release-bundle-cosign.pub` in the active checkout

## Converge

Before the first ADR 0233 replay, bootstrap the local signing material once:

```bash
python3 scripts/release_bundle.py init-signing
```

This writes:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/release-bundle-cosign.key`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/release-bundle-cosign.password.txt`
- `keys/gitea-release-bundle-cosign.pub` in the current checkout

Then run the managed converge so Gitea seeds the private repo Actions secrets:

```bash
ansible-playbook -i inventory/hosts.yml playbooks/gitea.yml
```

## Verify

1. Confirm the controller login page responds:

```bash
curl -sf http://100.64.0.1:3009/user/login >/dev/null
```

2. Confirm the mirrored admin token exists:

```bash
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/admin-token.txt
```

3. Confirm the runner token exists:

```bash
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/runner-registration-token.txt
```

4. Confirm the ADR 0233 signing material exists locally:

```bash
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/release-bundle-cosign.key
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/release-bundle-cosign.password.txt
test -s keys/gitea-release-bundle-cosign.pub
```

5. Confirm the build worker container is running:

```bash
ansible docker-build-lv3 -i inventory/hosts.yml -b -m command -a "docker ps --filter name=lv3-gitea-runner --format {{.Names}}"
```

5. Confirm the Gitea admin API sees the runner online:

```bash
export GITEA_TOKEN="$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/admin-token.txt)"
curl -sS \
  -H "Authorization: token ${GITEA_TOKEN}" \
  http://100.64.0.1:3009/api/v1/admin/actions/runners | \
  jq '{total_count, runners: [.runners[] | {name, status, busy, labels: [.labels[].name]}]}'
```

6. Confirm a branch push is accepted by the private repo gate and produces a successful Actions run:

```bash
export GITEA_TOKEN="$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/admin-token.txt)"
export GITEA_BASIC_AUTH="$(printf '%s:%s' 'ops-gitea' "${GITEA_TOKEN}" | base64)"
git -c http.extraHeader="Authorization: Basic ${GITEA_BASIC_AUTH}" \
  push http://100.64.0.1:3009/ops/proxmox_florin_server.git \
  HEAD:refs/heads/codex/gitea-runner-smoke

curl -sS \
  -H "Authorization: token ${GITEA_TOKEN}" \
  "http://100.64.0.1:3009/api/v1/repos/ops/proxmox_florin_server/actions/runs?limit=1" | \
  jq '{workflow_runs: [.workflow_runs[] | {id, status, conclusion, head_branch, head_sha}]}'
```

## Smoke-Test Repository Creation

Use the mirrored admin token to create a repository under the managed `ops` org:

```bash
export GITEA_TOKEN="$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/admin-token.txt)"
curl -sS \
  -H "Authorization: token ${GITEA_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"name":"ci-webhook-smoke","private":true,"auto_init":false}' \
  http://100.64.0.1:3009/api/v1/orgs/ops/repos
```

## Managed Hook Path

The repo-managed validation hook template lives at:

- `/opt/gitea/pre-receive.validation-hook`

The canonical repository hook is installed under:

- `/opt/gitea/data/git/repositories/ops/proxmox_florin_server.git/custom_hooks/pre-receive`

## Notes

- `git.lv3.org` is private-only. Do not add an NGINX edge publication for it.
- The bootstrap admin and runner registration tokens are mirrored locally for controlled operator workflows; keep `.local/gitea/` outside commits.
- ADR 0233 also seeds the private repo Actions secret `RELEASE_BUNDLE_REPO_TOKEN` from the mirrored Gitea admin token so server-resident workflows can publish and re-download private release assets during verification.
- The private git push path enforces the server-side validation gate before a ref is accepted. A rejected push can fail before any Actions workflow is created.
- The Gitea git SSH endpoint on port `2222` uses Gitea account keys, not the Proxmox host bootstrap key. For controlled automation from the operator workstation, the mirrored `ops-gitea` admin token over HTTP basic auth is the documented fallback.
- ADR 0233 reuses the managed Gitea bootstrap path to seed the private repo Actions secrets `RELEASE_BUNDLE_COSIGN_PRIVATE_KEY`, `RELEASE_BUNDLE_COSIGN_PASSWORD`, and `RELEASE_BUNDLE_REPO_TOKEN`.
- The signed bundle build, publish, and verification flow is documented in [signed-release-bundles.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/signed-release-bundles.md).
