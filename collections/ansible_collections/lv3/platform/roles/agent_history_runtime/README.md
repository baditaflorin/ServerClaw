# agent_history_runtime

ADR 0494. Converges the agent-history store on its dedicated guest (vmid 155): a compose project with Postgres 17 + pgvector,
`agent-store` and an OpenBao Agent; a LUKS2 data volume the owner unlocks by hand after every reboot; token files rendered from
OpenBao onto tmpfs; `tailscale serve` for the loopback listener; a metrics bridge and an optional nightly canary database scan.

Run it only through `playbooks/agent-history-vm.yml` (`make provision-agent-history-vm`), which limits the guests role to this vmid.
The runbook is `docs/runbooks/configure-agent-history.md`.

## What the role never does

- It never creates, copies, reads, prints or templates a secret value. The database password and the read, write and metrics tokens
  (and the embed token of the embedding worker) are created by the OpenBao administrator; the LUKS passphrase is typed by the owner into `agent-history-unlock` (standard input
  only); the tailnet join key and the AppRole files are delivered by the owner. Every template under `templates/*.ctmpl.j2` holds a
  KV path and key names only.
- It never formats a disk, and it never starts the compose project while `agent_history_data_mount` is not a mount point.
- It never publishes anything but the store on the loopback address; Postgres is on the compose network only.

## Layout on the guest

| Path | What |
|---|---|
| `/opt/agent-history/docker-compose.yml` | compose project (rendered only when `agent_history_store_image` is set) |
| `/opt/agent-history/openbao/` | `agent.hcl`, the secret templates, and the owner-delivered `role_id` and `secret_id` |
| `/run/<prefix>-secrets/agent-history/` | tmpfs: `db.env`, `store.env`, `read-tokens`, `write-tokens`, `metrics-token`, `embed-token`, `metrics.header` (all 0400, uid 65532) |
| `/srv/agent-history` | mount point of the unlocked volume (immutable while empty); Postgres data in `postgres/` |
| `/usr/local/sbin/agent-history-unlock` | the owner's unlock helper (passphrase on standard input) |
| `/usr/local/sbin/agent-history-metrics` | metrics bridge, run by `agent-history-metrics.timer` |

## Variables

See `defaults/main.yml` and `meta/argument_specs.yml`. Open questions are marked `TODO(ADR 0494 question N)`.

Semantic search is off until `agent_history_embed_url` and `agent_history_embed_model` are set (for this guest in `inventory/host_vars/agent-history.yml`). Then the store embeds each search question through that endpoint (`agent_history_embed_api`,
`_dimensions`, `_timeout`, `_cache_size`); a slow or unreachable endpoint degrades the search to text and exact instead of failing. The
`embed_tokens` key of the OpenBao entry is rendered to `embed-token` and passed as `-embedTokenFile`; the embedding worker uses it for
`/v1/embed/*` and nothing else. Plain `http://` is accepted only for a loopback, private or tailnet (100.64.0.0/10) address.

## Verification

`tasks/verify.yml` runs when the stack was started: health on loopback, loopback-only listeners and no Postgres listener, secret file
ownership and mode (never content), the Postgres directory on `/dev/mapper/agent-history-data`, and no swap.
The role has not been run on a guest; see the pull request for what is unverified.
