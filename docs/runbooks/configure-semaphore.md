# Configure Semaphore

## Purpose

This runbook defines the repo-managed Semaphore controller for private Ansible
job management on `runtime-control`.

Semaphore stays private-only on this platform. Repository automation remains the
source of truth; Semaphore provides a bounded UI and API for running
repo-managed jobs with Keycloak OIDC for routine operator sign-in and a
repo-managed fallback admin login for recovery.

## Canonical Surfaces

- playbook: [playbooks/semaphore.yml](../../playbooks/semaphore.yml)
- service wrapper: [playbooks/services/semaphore.yml](../../playbooks/services/semaphore.yml)
- runtime roles: [semaphore_postgres](../../collections/ansible_collections/lv3/platform/roles/semaphore_postgres) and [semaphore_runtime](../../collections/ansible_collections/lv3/platform/roles/semaphore_runtime)
- Keycloak client task: [keycloak_runtime/tasks/semaphore_client.yml](../../collections/ansible_collections/lv3/platform/roles/keycloak_runtime/tasks/semaphore_client.yml)
- bootstrap helper: [scripts/semaphore_bootstrap.py](../../scripts/semaphore_bootstrap.py)
- governed wrapper: [scripts/semaphore_tool.py](../../scripts/semaphore_tool.py)
- controller-local auth artifacts: `.local/semaphore/`
- controller-local Keycloak client secret: `.local/keycloak/semaphore-client-secret.txt`

## Access Model

- Semaphore is published only through the private controller URL exposed by the
  Proxmox host Tailscale proxy.
- `playbooks/semaphore.yml` reconciles the dedicated Keycloak `semaphore`
  client before the runtime converge and mirrors its secret under
  `.local/keycloak/semaphore-client-secret.txt`.
- the controller-local bootstrap artifacts stay under `.local/semaphore/`
  and power the governed `make semaphore-manage ...` wrapper
- the seeded project uses a repo-staged local checkout and the
  `Semaphore Self-Test` template to verify the Ansible job path
- broader infrastructure jobs stay repo-managed and must be added deliberately
  with explicit inventory and secret boundaries

## Primary Commands

Syntax-check the workflow:

```bash
make syntax-check-semaphore
```

Converge Semaphore live:

```bash
make converge-semaphore env=production
```

List Semaphore projects:

```bash
make semaphore-manage ACTION=list-projects
```

List templates in the seeded project:

```bash
make semaphore-manage ACTION=list-templates SEMAPHORE_ARGS='--project "LV3 Semaphore"'
```

Run the seeded self-test template and wait for completion:

```bash
make semaphore-manage ACTION=run-template SEMAPHORE_ARGS='--template "Semaphore Self-Test" --wait'
```

Read task output for one run:

```bash
make semaphore-manage ACTION=task-output SEMAPHORE_ARGS='--task-id 1'
```

## Verification

After a converge:

1. `make syntax-check-semaphore`
2. `SEMAPHORE_BASE_URL="$(jq -r '.base_url' .local/semaphore/admin-auth.json)"`
3. `curl -fsS "$SEMAPHORE_BASE_URL/api/ping"`
4. `curl -fsSI "$SEMAPHORE_BASE_URL/auth/oidc/login"`
5. `make semaphore-manage ACTION=list-projects`
6. `make semaphore-manage ACTION=run-template SEMAPHORE_ARGS='--template "Semaphore Self-Test" --wait'`

## Operating Rules

- keep Semaphore private-only
- let `playbooks/semaphore.yml` own the dedicated Keycloak client; do not
  create or store ad hoc Semaphore OIDC secrets under `.local/semaphore/`
- use the seeded project and governed CLI wrapper to verify API and job-runner health
- treat new inventories, SSH credentials, and broader infrastructure templates as explicit follow-up work, not implicit bootstrap scope
- if the Semaphore Keycloak client secret is rotated or exposed, refresh the
  repo-managed mirror with `make converge-semaphore env=production`
- document any emergency UI-authored mutation immediately and bring it back to repo truth in the same turn

## Troubleshooting

### Keycloak readiness probe fails during converge

If `make converge-semaphore env=production` fails while waiting for the Keycloak
readiness endpoint, recover the Keycloak compose stack on `docker-runtime`:

```bash
sudo docker compose -f /opt/keycloak/docker-compose.yml up -d --force-recreate
curl -fsS http://127.0.0.1:19000/health/ready
```

Re-run the converge once the readiness endpoint responds.

### Docker runtime compose stacks stopped after recovery

If the Docker runtime recovery leaves other compose stacks stopped (for example
`mail-platform` or `netbox`), restart them before re-running the converge:

```bash
sudo docker compose -f /opt/mail-platform/docker-compose.yml up -d
sudo docker compose -f /opt/netbox/docker-compose.yml up -d
```
