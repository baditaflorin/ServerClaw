# Configure Label Studio

Label Studio is the repo-managed human-in-the-loop data annotation platform
published at `https://annotate.example.com`. The runtime lives on
`docker-runtime`, stores its state in the dedicated PostgreSQL database
`label_studio` on `postgres`, and uses the shared edge oauth2-proxy plus
Keycloak browser-auth boundary while preserving app-local admin and token auth
for Community Edition-compatible automation and break-glass recovery.

## Repo Surfaces

- Root playbook: `playbooks/label-studio.yml`
- Service wrapper: `playbooks/services/label-studio.yml`
- Runtime role: `roles/label_studio_runtime/`
- PostgreSQL role: `roles/label_studio_postgres/`
- Project sync helper: `scripts/label_studio_sync.py`

## Implementation Variance From ADR 0289

- Browser sign-in is enforced at the shared edge through oauth2-proxy and
  Keycloak, not by a first-class in-app OIDC client. This keeps the published
  UI protected while avoiding Community Edition auth drift.
- Repo automation continues to use the Label Studio admin password and legacy
  API token surfaces for deterministic project-catalog sync and post-apply
  verification.
- The repo-managed contract focuses on deterministic project definitions and
  private API verification. Downstream dataset export into MinIO or MLflow
  remains an automation consumer concern rather than a runtime bootstrap step.

## Controller-Local Artifacts

The converge path creates and reuses these controller-local files:

- `.local/label-studio/database-password.txt`
- `.local/label-studio/admin-password.txt`
- `.local/label-studio/admin-token.txt`

## Converge

Run the syntax check first:

```bash
make syntax-check-label-studio
```

Run the preflight so the shared edge bootstrap artifacts are present before the
live converge:

```bash
make preflight WORKFLOW=converge-label-studio
```

Run the live converge from the repo root:

```bash
make converge-label-studio env=production
```

`converge-label-studio` requires:

- `BOOTSTRAP_KEY` or the default controller SSH key path
- `HETZNER_DNS_API_TOKEN` in the environment so the playbook can publish
  `annotate.example.com`

The playbook performs these steps:

1. Ensures the `annotate.example.com` Hetzner DNS record exists.
2. Creates or reconciles the PostgreSQL role and dedicated `label_studio`
   database on `postgres`.
3. Creates the runtime secrets, compose env, project catalog, and Label Studio
   runtime on `docker-runtime`.
4. Reconciles the shared Typesense runtime on `docker-runtime` before the
   API gateway structured-search catalog refresh runs.
5. Reconciles the repo-managed project catalog through the private Label Studio
   admin token.
6. Publishes Label Studio through the shared NGINX edge and verifies the public
   UI and API redirect into the shared auth boundary.

## Verification

Guest-local runtime verification:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'docker compose --file /opt/label-studio/docker-compose.yml ps && curl -fsS http://127.0.0.1:8110/api/version'
```

Guest-local private API verification with the repo-managed admin token:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'TOKEN=$(sudo cat /etc/lv3/label-studio/admin-token.txt); curl -fsS -H "Authorization: Token $TOKEN" http://127.0.0.1:8110/api/projects'
```

Public shared-edge verification:

```bash
curl -I https://annotate.example.com/
curl -I https://annotate.example.com/api/projects
```

Project-catalog verification directly through the helper on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.20 \
  'sudo python3 /srv/proxmox-host_server/scripts/label_studio_sync.py verify \
    --base-url http://127.0.0.1:8110 \
    --token-file /etc/lv3/label-studio/admin-token.txt \
    --project-catalog /opt/label-studio/project-catalog.json \
    --report-file /opt/label-studio/verify-report.json && \
   sudo cat /opt/label-studio/verify-report.json'
```

The verification helper checks:

- `GET /api/version`
- token-authenticated `GET /api/projects`
- repo-managed project ids, titles, and label config content

## Recovery Notes

- Re-run `make converge-label-studio` for drift correction or after rebuilding
  `docker-runtime`, `postgres`, or the shared edge configuration.
- `make converge-label-studio` now also replays the shared Typesense runtime on
  `docker-runtime`, so it is the preferred recovery path when a Docker
  daemon restart or firewall reconciliation leaves the API gateway structured
  search dependency unavailable.
- If the public UI or API stops redirecting through oauth2-proxy, reconverge
  `make converge-keycloak env=production`, then rerun
  `make converge-label-studio`. The shared auth boundary can drift even when
  the Label Studio private runtime itself is healthy.
- If the private API works but the public redirect fails, inspect the Label
  Studio `annotate.example.com` edge publication and oauth2-proxy routing before
  changing in-app auth.
- If project sync fails after a Label Studio upgrade, inspect
  `/opt/label-studio/project-catalog.json`, rerun the private token-backed
  `scripts/label_studio_sync.py verify` command above, and only then widen the
  role defaults or helper compatibility logic.
