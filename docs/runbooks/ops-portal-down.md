# Ops Portal Down

## Purpose

Recover the interactive ops portal runtime when `ops.lv3.org` or the local `http://10.10.10.20:8092/health` probe fails.

## Symptoms

- `https://ops.lv3.org/health` no longer returns `200`
- the portal renders an NGINX `502` or the login flow completes but the app shell never loads
- the login flow redirects to `/oauth2/callback?...error=invalid_scope`
- the Keycloak login form accepts a submit and then renders `We are sorry... Unexpected error when handling authentication request to identity provider.`
- password reset or required-action flows claim success but the reset email never arrives
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

4. If the portal redirects to Keycloak but the submit fails, check the Keycloak runtime directly:

```bash
curl -I https://sso.lv3.org/realms/lv3/.well-known/openid-configuration
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p' \
  ops@10.10.10.20 \
  'docker logs --tail 80 keycloak-keycloak-1'
```

If the logs show `Acquisition timeout while waiting for new connection`, the JDBC pool is wedged. If a restart then fails with `No chain/target/match by that name`, Docker's nat chain on `docker-runtime-lv3` is missing and Keycloak must be recreated after Docker itself is restarted.

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

4. If the callback includes `error=invalid_scope`, verify the rendered oauth2-proxy config on `nginx-lv3` does not request a custom `groups` scope. The portal relies on a client-mapped `groups` claim, so the requested scope must stay `openid profile email` unless a real Keycloak client scope named `groups` is added and assigned.

5. If the auth failure is actually Keycloak, recover the runtime from the Proxmox host through the guest agent:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  root@100.118.189.95 \
  "qm guest exec 120 -- /bin/sh -lc 'systemctl restart docker'"

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  root@100.118.189.95 \
  \"qm guest exec 120 -- /bin/sh -lc 'cd /opt/keycloak && docker compose up -d --force-recreate keycloak'\"
```

6. Re-verify the IdP and portal redirect path:

```bash
curl -I https://sso.lv3.org/realms/lv3/.well-known/openid-configuration
curl -I https://ops.lv3.org/oauth2/sign_in
```

7. If login is healthy but password-reset mail is still broken, verify the realm SMTP path and the private relay on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p' \
  ops@10.10.10.20 \
  'python3 - <<'"'"'PY'"'"'\nimport smtplib\nfrom pathlib import Path\npassword = Path("/etc/lv3/mail-platform/server-mailbox-password").read_text().strip()\nclient = smtplib.SMTP("10.10.10.20", 1587, timeout=10)\nclient.ehlo()\nprint(client.login("server", password))\nclient.quit()\nPY'

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.118.189.95 -W %h:%p' \
  ops@10.10.10.20 \
  'docker logs --tail 120 keycloak-keycloak-1 | grep -i -E "smtp|reset_password|required.action"'
```

Use the base login URLs (`https://ops.lv3.org` or `https://ops.lv3.org/oauth2/sign_in`) when retesting. A stale `login-actions/...` or `reset-credentials?...` URL without the matching browser cookie can still render Keycloak's generic `We are sorry...` page even when the live service is healthy.

## Static Fallback

The legacy generated portal landing page is archived at `receipts/ops-portal-snapshot.html`. Use it as a read-only fallback when the interactive runtime is unavailable.
