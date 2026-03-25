# Configure Langfuse

This runbook covers the repo-managed Langfuse deployment introduced by [ADR 0146](/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/adr-0146-ai-observability/docs/adr/0146-langfuse-for-agent-observability.md).

## Scope

The Langfuse workflow converges:

- the PostgreSQL backend on `postgres-lv3`
- the Langfuse runtime on `docker-runtime-lv3`
- the public hostname `langfuse.lv3.org` on the shared NGINX edge
- the Keycloak OIDC client used by the Langfuse sign-in flow
- the repo-managed bootstrap org, project, API keys, and bootstrap user

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload is already available under `.local/openbao/init.json`
- Keycloak is already deployed and healthy on `sso.lv3.org`
- Hetzner DNS API credentials are available when the edge certificate needs expansion

## Converge

Run:

```bash
HETZNER_DNS_API_TOKEN=... make converge-langfuse
```

## Generated local artifacts

The workflow maintains controller-local secrets under `.local/langfuse/`:

- `database-password.txt`
- `nextauth-secret.txt`
- `salt.txt`
- `encryption-key.txt`
- `clickhouse-password.txt`
- `redis-password.txt`
- `minio-root-password.txt`
- `bootstrap-user-password.txt`
- `project-public-key.txt`
- `project-secret-key.txt`

The Keycloak client secret is mirrored under `.local/keycloak/langfuse-client-secret.txt`.

## Verification

Repository and syntax checks:

```bash
make syntax-check-langfuse
```

Runtime and API verification:

```bash
curl -fsS https://langfuse.lv3.org/api/public/health
uv run --with langfuse --with requests python scripts/langfuse_trace_smoke.py \
  --base-url https://langfuse.lv3.org \
  --project-id lv3-agent-observability \
  --bootstrap-email baditaflorin@gmail.com \
  --bootstrap-password-file .local/langfuse/bootstrap-user-password.txt
```

The smoke script emits one synthetic trace, polls the Langfuse public API until the trace is readable, and prints the direct UI URL for that trace. When bootstrap credentials are provided, it also verifies that the trace page resolves through the Langfuse HTML UI.
