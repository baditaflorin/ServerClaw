# Configure Gitea

This runbook covers the private Gitea deployment introduced by ADR 0143.

## Purpose

`git.lv3.org` provides the self-hosted Git and CI surface for LV3. It runs privately on `docker-runtime-lv3`, uses PostgreSQL on `postgres-lv3`, authenticates operators through Keycloak, and dispatches Actions jobs to `docker-build-lv3`.

## Managed Paths

- Runtime host: `docker-runtime-lv3`
- Database host: `postgres-lv3`
- Runner host: `docker-build-lv3`
- Controller URL: `http://100.64.0.1:3009`
- Shared local bootstrap artifacts: `$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.local/gitea/`

## Converge

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
export LV3_GIT_COMMON_ROOT="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
test -s "${LV3_GIT_COMMON_ROOT}/.local/gitea/admin-token.txt"
```

3. Confirm the runner token exists:

```bash
test -s "${LV3_GIT_COMMON_ROOT}/.local/gitea/runner-registration-token.txt"
```

4. Confirm the build worker container is running:

```bash
ansible docker-build-lv3 -i inventory/hosts.yml -b -m command -a "docker ps --filter name=lv3-gitea-runner --format {{.Names}}"
```

5. Confirm the Renovate token is mirrored locally:

```bash
test -s "${LV3_GIT_COMMON_ROOT}/.local/gitea/renovate-token.txt"
```

## Smoke-Test Repository Creation

Use the mirrored admin token to create a repository under the managed `ops` org:

```bash
export GITEA_TOKEN="$(tr -d '\n' < "${LV3_GIT_COMMON_ROOT}/.local/gitea/admin-token.txt")"
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
- The bootstrap admin, runner, and Renovate tokens are mirrored under the shared git common-root `.local/gitea/` path so every worktree can reuse the same controller-local artifacts safely; keep that directory outside commits.
- The internal `ops/proxmox_florin_server` repository path is created by the Gitea bootstrap, but repository contents are published separately through `make publish-gitea-repo` so the workflow source stays tied to an explicit checkout and ref.
- ADR 0195 adds a dedicated `renovate-bot` token and repository Actions secret through the same converge path; see [configure-renovate.md](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/docs/runbooks/configure-renovate.md) for the follow-on publish and workflow verification steps.
