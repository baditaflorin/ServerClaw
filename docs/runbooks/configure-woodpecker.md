# Configure Woodpecker

## Purpose

This runbook defines the repo-managed Woodpecker CI runtime for event-driven validation and governed pipeline execution on `docker-runtime-lv3`.

Woodpecker is public on this platform at `ci.lv3.org`, but repository activation, secret management, and manual pipeline control remain repo-managed through the Gitea and Woodpecker APIs.

## Canonical Surfaces

- playbook: [playbooks/woodpecker.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/woodpecker.yml)
- roles: [roles/woodpecker_postgres](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/woodpecker_postgres) and [roles/woodpecker_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/woodpecker_runtime)
- bootstrap helper: [scripts/woodpecker_bootstrap.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/woodpecker_bootstrap.py)
- governed wrapper: [scripts/woodpecker_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/woodpecker_tool.py)
- repository pipeline: [.woodpecker.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.woodpecker.yml)
- controller-local auth artifacts: `.local/woodpecker/`

## Access Model

- public browser and API surface: `https://ci.lv3.org`
- private controller path: `http://100.64.0.1:8017`
- the Woodpecker login flow delegates to the repo-managed Gitea OAuth application
- controller-local auth artifacts are mirrored under `.local/woodpecker/`
- the seeded repository is `ops/proxmox_florin_server`
- the seeded repository secret `LV3_WOODPECKER_SECRET_SMOKE` is used only for governed CI smoke verification

## Generated Local Artifacts

The workflow maintains controller-local artifacts under `.local/woodpecker/`:

- `database-password.txt`
- `gitea-client-id.txt`
- `gitea-client-secret.txt`
- `agent-secret.txt`
- `api-token.txt`
- `admin-auth.json`
- `bootstrap-spec.json`
- `repo-secret-smoke.txt`

## Primary Commands

Syntax-check the workflow:

```bash
make syntax-check-woodpecker
```

Converge Woodpecker live:

```bash
HETZNER_DNS_API_TOKEN=... make converge-woodpecker
```

The edge publication replay now falls back to a dedicated site-local
certificate for `ci.lv3.org` when the shared `lv3-edge` certificate does not
yet contain the Woodpecker hostname. This keeps Woodpecker live even if
unrelated SAN expansion on the shared edge certificate is temporarily blocked.

Show the bootstrap identity:

```bash
make woodpecker-manage ACTION=whoami
```

List repositories visible to the managed identity:

```bash
make woodpecker-manage ACTION=list-repos
```

List seeded repository secrets:

```bash
make woodpecker-manage ACTION=list-secrets WOODPECKER_ARGS='--repo ops/proxmox_florin_server'
```

Trigger the seeded repository pipeline and wait:

```bash
make woodpecker-manage ACTION=trigger-pipeline WOODPECKER_ARGS='--repo ops/proxmox_florin_server --branch main --wait'
```

If the target forge branch does not yet contain `.woodpecker.yml`, Woodpecker
accepts the manual trigger request with `204 No Content` but no pipeline run
appears. Push or merge the branch carrying `.woodpecker.yml` first, then rerun
the managed trigger command.

## Verification

After a converge:

1. `make syntax-check-woodpecker`
2. `curl -fsS http://100.64.0.1:8017/healthz`
3. `curl -fsS https://ci.lv3.org/healthz`
4. `openssl s_client -connect ci.lv3.org:443 -servername ci.lv3.org </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -ext subjectAltName`
5. `make woodpecker-manage ACTION=whoami`
6. `make woodpecker-manage ACTION=list-secrets WOODPECKER_ARGS='--repo ops/proxmox_florin_server'`
7. `make woodpecker-manage ACTION=trigger-pipeline WOODPECKER_ARGS='--repo ops/proxmox_florin_server --branch main --wait'`
8. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'docker compose --file /opt/woodpecker/docker-compose.yml ps && sudo ls -l /run/lv3-secrets/woodpecker /etc/lv3/woodpecker /opt/woodpecker/data'`

## Operating Rules

- keep repository activation, secret management, and manual pipeline runs on the repo-managed API path
- treat `.woodpecker.yml` as the source of truth for repository validation behavior
- keep the Gitea OAuth client and Woodpecker API token in controller-local managed artifacts instead of ad hoc browser state
- document any emergency UI-authored mutation immediately and bring it back to repo truth in the same turn
