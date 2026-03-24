# Ops Portal Down

## Purpose

Recover the interactive ops portal runtime when `ops.lv3.org` or the local `http://10.10.10.20:8092/health` probe fails.

## Symptoms

- `https://ops.lv3.org/health` no longer returns `200`
- the portal renders an NGINX `502` or the login flow completes but the app shell never loads
- `docker compose ps` on `docker-runtime-lv3` shows the `ops-portal` container exited or unhealthy

## Immediate Checks

1. Verify the local runtime on `docker-runtime-lv3`:

```bash
ssh ops@100.118.189.95 'ssh ops@10.10.10.20 "docker compose -f /opt/ops-portal/docker-compose.yml ps"'
```

2. Verify the local health endpoint:

```bash
ssh ops@100.118.189.95 'ssh ops@10.10.10.20 "curl -sf http://10.10.10.20:8092/health"'
```

3. Verify the edge can still reach the runtime:

```bash
ssh ops@100.118.189.95 'ssh ops@10.10.10.10 "curl -k -I -H \"Host: ops.lv3.org\" https://127.0.0.1/health"'
```

## Recovery

1. Re-apply the portal runtime:

```bash
ansible-playbook playbooks/ops-portal.yml
```

2. If the runtime is healthy locally but the public hostname fails, re-apply the edge:

```bash
ansible-playbook playbooks/public-edge.yml
```

3. If gateway-backed actions fail while the UI shell loads, confirm the configured `GATEWAY_URL` from `/opt/ops-portal/ops-portal.env` and verify the API gateway separately before restarting the portal.

## Static Fallback

The legacy generated portal landing page is archived at `receipts/ops-portal-snapshot.html`. Use it as a read-only fallback when the interactive runtime is unavailable.
