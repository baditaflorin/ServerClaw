# Configure Temporal

## Purpose

Operate the private Temporal runtime that implements ADR 0293's durable
workflow and task-queue engine while keeping its PostgreSQL bootstrap,
namespace contract, and smoke verification replayable from the repository.

## Repo Sources Of Truth

- `playbooks/temporal.yml`
- `playbooks/services/temporal.yml`
- `collections/ansible_collections/lv3/platform/roles/temporal_postgres/`
- `collections/ansible_collections/lv3/platform/roles/temporal_runtime/`
- `scripts/temporal_smoke.py`

## Preconditions

- OpenBao is already converged and the controller has `.local/openbao/init.json`.
- PostgreSQL and `runtime-control` are reachable through the standard
  Proxmox jump path.
- The controller can run `uv run --with temporalio`.

## Converge

Run:

```bash
make converge-temporal env=production
```

The converge flow:

- provisions the `temporal` and `temporal_visibility` PostgreSQL databases
- bootstraps the Temporal SQL schema and records a controller-local schema
  bootstrap report
- deploys the Temporal runtime on `runtime-control`
- writes the runtime database password through the OpenBao compose env helper
- bootstraps the repo-managed `lv3` namespace with a 7-day retention policy
- records the namespace description under `.local/temporal/namespace-report.json`

## Verify

Run:

```bash
make syntax-check-temporal
ANSIBLE_HOST_KEY_CHECKING=False ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/inventory/hosts.yml runtime-control \
  -m shell \
  -a 'docker compose -f /opt/temporal/docker-compose.yml ps && docker compose -f /opt/temporal/docker-compose.yml --profile tools run --rm temporal-admin-tools temporal operator cluster health && docker compose -f /opt/temporal/docker-compose.yml --profile tools run --rm temporal-admin-tools temporal operator namespace describe --namespace lv3' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand="ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o LogLevel=ERROR -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p" \
  -L 17233:127.0.0.1:7233 \
  -L 18099:127.0.0.1:8099 \
  ops@10.10.10.92
```

In another shell, after the tunnel is active:

```bash
uv run --with temporalio python scripts/temporal_smoke.py --address 127.0.0.1:17233 --namespace lv3
curl -fsS http://127.0.0.1:18099
```

Expected results:

- the smoke script returns JSON with a workflow id, run id, task queue, and a
  `temporal-smoke:<name>` activity result
- the Temporal UI renders through the loopback tunnel on `http://127.0.0.1:18099`
- `docker compose --profile tools --file /opt/temporal/docker-compose.yml run --rm temporal-admin-tools temporal operator cluster health`
  succeeds on `runtime-control`
- `docker compose --profile tools --file /opt/temporal/docker-compose.yml run --rm temporal-admin-tools temporal operator namespace describe --namespace lv3`
  succeeds on `runtime-control`

If the controller-local SDK smoke sees a transient gRPC connection reset
immediately after a forced recreate, wait a few seconds and rerun it after the
frontend finishes warming up. The on-guest admin-tools health checks and the
recorded smoke receipt remain the authoritative live-apply evidence.

## Controller Artifacts

- `.local/temporal/database-password.txt`
- `.local/temporal/schema-bootstrap-report.json`
- `.local/temporal/namespace-report.json`
- `receipts/live-applies/evidence/2026-03-30-ws-0293-converge-temporal-r14.txt`
- `receipts/live-applies/evidence/2026-03-30-ws-0293-temporal-smoke-r14-remote.json`

## Recovery Notes

- Re-run `make converge-temporal env=production` instead of hand-editing the
  Temporal databases, runtime config, or namespace retention.
- The live-apply path checks schema tables locally on `postgres` as the
  `postgres` user and can stop the Temporal stack before schema migrations if
  the shared PostgreSQL cluster runs out of regular connection slots.
- The Temporal frontend gRPC port `7233`, frontend HTTP port `7243`, and the UI
  port `8099` are intentionally loopback-only on `runtime-control`; use SSH
  tunneling for diagnostics instead of broadening the guest firewall ad hoc.
- If the controller-local database password is lost, delete
  `.local/temporal/database-password.txt` and replay the converge from git so
  the postgres role and runtime secret injection stay aligned.
- The SQL schema bootstrap uses the official `temporalio/admin-tools` image and
  embedded `postgresql/v12` schema directories; avoid mixing in ad hoc schema
  files or manual `psql` DDL when recovering the service.
