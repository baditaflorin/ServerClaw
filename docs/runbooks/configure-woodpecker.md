# Configure Woodpecker

## Purpose

This runbook defines the repo-managed Woodpecker CI runtime for event-driven validation and governed pipeline execution on `docker-runtime`.

Woodpecker is public on this platform at `ci.example.com`, but repository activation, secret management, and manual pipeline control remain repo-managed through the Woodpecker API. The forge is GitHub, not Gitea (see "Which forge" below).

## Which forge

Verified on 2026-10-30: both CI planes use a **GitHub** forge.

- `ci.0mcp` (`https://ci.example.org`) and `ci.0exec` (`https://ci.0exec.com`): `GET /api/user` with the admin token returns an `avatar_url` on `avatars.githubusercontent.com` and `admin: true`; repositories carry a `forge_url` of the form `https://github.com/OWNER/REPO`.
- The agent address `10.10.10.20:9000` is the gRPC port, not the HTTP API; use the `https://` URLs above.

Not verified: that anything in this repo's `woodpecker_runtime` role, `scripts/woodpecker_bootstrap.py` or the Gitea-era sections of ADR 0287 still describes a running plane. They configure a Gitea OAuth application and were not changed. `scripts/woodpecker_tool.py activate-repo` is the same Gitea-era path (it reads a Gitea API URL and token from `.local/woodpecker/admin-auth.json` and looks the repository up in Gitea); it does not work against the GitHub planes. Use "Activate a repository" below.

## Activate a repository

From the operator's Mac (needs `ssh` to the bastion and an authenticated `gh`):

```bash
scripts/woodpecker_activate_repo.sh ci.0mcp baditaflorin/0pipe            # activate if missing; already activated is a no-op
scripts/woodpecker_activate_repo.sh ci.0exec OWNER/REPO --run main         # also trigger a pipeline on main, wait, print each step
```

What it does: it asks the server first (`GET /api/user`; prints the forge and whether the token is admin, and refuses unless the forge is GitHub), looks the repository up (`GET /api/repos/lookup/OWNER/REPO`, 404 means not activated), activates a missing one with `POST /api/repos?forge_remote_id=<GitHub numeric id from gh api repos/OWNER/REPO --jq .id>`, and with `--run` triggers `POST /api/repos/<id>/pipelines` with `{"branch": ...}` and polls the pipeline. Exit 0 means activated (and, with `--run`, the pipeline succeeded).

| Plane | URL | Fleet-vault entry (read on CT108) | Notes |
|---|---|---|---|
| `ci.0mcp` | `https://ci.example.org` | `woodpecker-ci-0mcp-api-token` | reachable from CT108 directly |
| `ci.0exec` | `https://ci.0exec.com` | `woodpecker_ci_admin_pat_for_ci_0exec_com` | from CT108 only through the tailnet proxy `http://127.0.0.1:1056` |

How the token is handled: every API call is made by `curl` inside CT108 (`ssh 0docker_bastion "pct exec 108 -- bash -s"`). The remote shell reads the entry with `bash /root/bin/fv.sh raw <entry>` into a variable and gives it to curl on stdin (`curl -K -`). It never reaches the Mac, a command line, a file or the output. Do not add `set -x`, do not put the token in a `-H` argument, and do not read the entry by hand to "just check".

Webhook-token caution: activation makes Woodpecker create a GitHub webhook whose URL contains a hook token, and the activation response carries hook fields. The script prints neither. If you activate by hand, do not print the response or the webhook URL, and do not paste them into a ticket or a chat.

Reference: `baditaflorin/0pipe` was activated on `ci.0mcp` this way on 2026-10-30 (Woodpecker repo id 6). Not verified: the `--run` polling uses `GET /api/repos/<id>/pipelines/<number>`; the scripted run of the whole flow is tested offline only (`tests/test_woodpecker_activate_repo.py`, shims for `ssh`, `gh` and `curl`).

## Trigger Filters

Keep the main validation event filter on the `validate-woodpecker-contract`
step, using a step-level `when` list for `manual`, `push`, and `pull_request`.
Do not move this filter to the workflow root: the deployed server ignored push
and pull-request webhooks with `when filters filtered out all steps`, leaving
the GitHub checks pending even though an eligible validation step was defined.
`tests/test_woodpecker_workflow_contract.py` guards this configuration shape.

## Canonical Surfaces

- playbook: [playbooks/woodpecker.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/playbooks/woodpecker.yml)
- roles: [roles/woodpecker_postgres](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/woodpecker_postgres) and [roles/woodpecker_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/roles/woodpecker_runtime)
- bootstrap helper: [scripts/woodpecker_bootstrap.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/woodpecker_bootstrap.py)
- governed wrapper: [scripts/woodpecker_tool.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/scripts/woodpecker_tool.py)
- repository pipeline: [.woodpecker.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.woodpecker.yml)
- controller-local auth artifacts: `.local/woodpecker/`

## Access Model

- public browser and API surface: `https://ci.example.com`
- private controller path: `http://100.64.0.1:8017`
- the Woodpecker login flow delegates to the forge, which is GitHub on both production planes (see "Which forge"); the Gitea OAuth application described in older versions of this runbook and in ADR 0287 is the original design, not the verified state
- controller-local auth artifacts are mirrored under `.local/woodpecker/`
- the seeded repository is `ops/proxmox-host_server`
- the seeded repository secret `LV3_WOODPECKER_SECRET_SMOKE` is used only for governed CI smoke verification

## Generated Local Artifacts

The `woodpecker_runtime` role and `scripts/woodpecker_bootstrap.py` (Gitea-era code, kept as it is) maintain controller-local artifacts under `.local/woodpecker/`; the two `gitea-client-*` files belong to that Gitea path and are not used by the GitHub-forge planes:

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
certificate for `ci.example.com` when the shared `lv3-edge` certificate does not
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
make woodpecker-manage ACTION=list-secrets WOODPECKER_ARGS='--repo ops/proxmox-host_server'
```

Trigger the seeded repository pipeline and wait:

```bash
make woodpecker-manage ACTION=trigger-pipeline WOODPECKER_ARGS='--repo ops/proxmox-host_server --branch main --wait'
```

If the target forge branch does not yet contain `.woodpecker.yml`, Woodpecker
accepts the manual trigger request with `204 No Content` but no pipeline run
appears. Push or merge the branch carrying `.woodpecker.yml` first, then rerun
the managed trigger command.

If `origin/main` already contains `.woodpecker.yml` and the managed trigger
still returns an accepted response while `make woodpecker-manage
ACTION=list-pipelines WOODPECKER_ARGS='--repo ops/proxmox-host_server
--branch main'` keeps returning `[]`, treat that as a Woodpecker
post-acceptance visibility issue. Capture:

```bash
make woodpecker-manage ACTION=trigger-pipeline WOODPECKER_ARGS='--repo ops/proxmox-host_server --branch main'
make woodpecker-manage ACTION=list-pipelines WOODPECKER_ARGS='--repo ops/proxmox-host_server --branch main'
make woodpecker-manage ACTION=trigger-pipeline WOODPECKER_ARGS='--repo ops/proxmox-host_server --branch main --wait --timeout 30'
```

Then inspect the live runtime on `docker-runtime` with the jump-path check
already documented below to review `docker compose --file
/opt/woodpecker/docker-compose.yml ps` and the Woodpecker container logs before
claiming end-to-end pipeline visibility is healthy again.

## Verification

After a converge:

1. `make syntax-check-woodpecker`
2. `curl -fsS http://100.64.0.1:8017/healthz`
3. `curl -fsS https://ci.example.com/healthz`
4. `openssl s_client -connect ci.example.com:443 -servername ci.example.com </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -ext subjectAltName`
5. `make woodpecker-manage ACTION=whoami`
6. `make woodpecker-manage ACTION=list-secrets WOODPECKER_ARGS='--repo ops/proxmox-host_server'`
7. `make woodpecker-manage ACTION=trigger-pipeline WOODPECKER_ARGS='--repo ops/proxmox-host_server --branch main --wait'`
8. `ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -J ops@100.64.0.1 ops@10.10.10.20 'docker compose --file /opt/woodpecker/docker-compose.yml ps && sudo ls -l /run/lv3-secrets/woodpecker /etc/lv3/woodpecker /opt/woodpecker/data'`

## Operating Rules

- keep repository activation, secret management, and manual pipeline runs on the repo-managed API path
- treat `.woodpecker.yml` as the source of truth for repository validation behavior
- keep the Woodpecker API token in fleet-vault (production planes) or controller-local managed artifacts instead of ad hoc browser state
- document any emergency UI-authored mutation immediately and bring it back to repo truth in the same turn
