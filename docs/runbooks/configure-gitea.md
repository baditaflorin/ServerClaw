# Configure Gitea

This runbook covers the private Gitea deployment introduced by ADR 0143.

## Purpose

`git.lv3.org` provides the self-hosted Git and CI surface for LV3. It runs privately on `docker-runtime-lv3`, uses PostgreSQL on `postgres-lv3`, authenticates operators through Keycloak, and dispatches Actions jobs to `docker-build-lv3`.

## Managed Paths

- Runtime host: `docker-runtime-lv3`
- Database host: `postgres-lv3`
- Runner host: `docker-build-lv3`
- Controller URL: `http://100.118.189.95:3009`
- Local bootstrap artifacts: `/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/`

## Converge

```bash
ansible-playbook -i inventory/hosts.yml playbooks/gitea.yml
```

## Verify

1. Confirm the controller login page responds:

```bash
curl -sf http://100.118.189.95:3009/user/login >/dev/null
```

2. Confirm the mirrored admin token exists:

```bash
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/admin-token.txt
```

3. Confirm the runner token exists:

```bash
test -s /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/runner-registration-token.txt
```

4. Confirm the build worker container is running:

```bash
ansible docker-build-lv3 -i inventory/hosts.yml -b -m command -a "docker ps --filter name=lv3-gitea-runner --format {{.Names}}"
```

## Smoke-Test Repository Creation

Use the mirrored admin token to create a repository under the managed `ops` org:

```bash
export GITEA_TOKEN="$(tr -d '\n' < /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/gitea/admin-token.txt)"
curl -sS \
  -H "Authorization: token ${GITEA_TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"name":"ci-webhook-smoke","private":true,"auto_init":false}' \
  http://100.118.189.95:3009/api/v1/orgs/ops/repos
```

## Managed Hook Path

The repo-managed validation hook template lives at:

- `/opt/gitea/pre-receive.validation-hook`

The canonical repository hook is installed under:

- `/opt/gitea/data/git/repositories/ops/proxmox_florin_server.git/custom_hooks/pre-receive`

## Notes

- `git.lv3.org` is private-only. Do not add an NGINX edge publication for it.
- The bootstrap admin and runner registration tokens are mirrored locally for controlled operator workflows; keep `.local/gitea/` outside commits.
