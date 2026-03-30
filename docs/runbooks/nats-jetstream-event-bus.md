# NATS JetStream Event Bus

## Purpose

This runbook covers the private NATS JetStream runtime that ADR 0276 makes the
platform event bus on `docker-runtime-lv3`.

It is the operational reference for:

- converging the repo-managed runtime under `/opt/nats-jetstream`
- reconciling the committed stream contract from `config/nats-streams.yaml`
- verifying the loopback health endpoint and the live stream registry
- confirming the current canonical subjects used by the platform mutation and
  secret-rotation publishers

## Canonical Sources

- runtime playbook: [playbooks/nats-jetstream.yml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/playbooks/nats-jetstream.yml)
- runtime role: [roles/nats_jetstream_runtime](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/roles/nats_jetstream_runtime)
- stream registry: [config/nats-streams.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/nats-streams.yaml)
- stream reconcile tool: [scripts/nats_streams.py](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/scripts/nats_streams.py)
- topic taxonomy: [config/event-taxonomy.yaml](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/config/event-taxonomy.yaml)

## Runtime Layout

- compose root: `/opt/nats-jetstream`
- server config: `/opt/nats-jetstream/config/nats-server.conf`
- JetStream data: `/opt/nats-jetstream/data`
- client listener: `127.0.0.1` or `10.10.10.20` on TCP `4222`
- monitoring endpoint: `http://127.0.0.1:8222/healthz`

The repo-managed runtime currently keeps one controller-known admin principal:

- `jetstream-admin` with the password mirrored at `.local/nats/jetstream-admin-password.txt`

That principal can manage JetStream and publish the current platform subject
families:

- `platform.>`
- `rag.document.>`
- `secret.rotation.>`

## Converge The Runtime

From a synchronized worktree:

```bash
ANSIBLE_HOST_KEY_CHECKING=False \
ansible-playbook -i inventory/hosts.yml playbooks/nats-jetstream.yml \
  --private-key .local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

The playbook:

1. ensures the controller-local admin password exists
2. renders `/opt/nats-jetstream/config/nats-server.conf`
3. renders `/opt/nats-jetstream/docker-compose.yml`
4. runs `docker compose pull`
5. runs `docker compose up -d --remove-orphans`
6. verifies `127.0.0.1:4222` and `http://127.0.0.1:8222/healthz`

## Reconcile Streams

Check the live streams:

```bash
make check-nats-streams
```

Apply the committed registry if drift or missing streams are reported:

```bash
make apply-nats-streams
```

The committed stream registry is:

- `PLATFORM_EVENTS` for all `platform.*` control-plane and mutation events
- `RAG_DOCUMENT` for `rag.document.*`
- `SECRET_ROTATION` for `secret.rotation.*`

`platform.mutation.recorded` intentionally remains inside `PLATFORM_EVENTS` so
the platform does not destroy and recreate the existing `platform.>` stream
history during ADR 0276 rollout.

## Verify End To End

1. `curl -fsS http://127.0.0.1:8222/healthz` on `docker-runtime-lv3`
2. `make check-nats-streams`
3. Publish one `platform.findings.observation` smoke record with `scripts/nats_streams.py --smoke-publish`
4. Publish one `secret.rotation.completed` and one `rag.document.staged` smoke record through a controller-side `nats-py` snippet when those domain streams are first reconciled
5. Record the live-apply receipt under `receipts/live-applies/`
