# Ops Portal Down

## Purpose

Recover the interactive ops portal runtime when `ops.lv3.org` or the local `http://10.10.10.20:8092/health` probe fails.

## Symptoms

- `https://ops.lv3.org/health` no longer returns `200`
- the portal renders an NGINX `502` or the login flow completes but the app shell never loads
- the portal shell loads but the chart panels stay blank or never repaint after section refreshes
- the overview loads but the runtime assurance scoreboard section is missing or
  empty
- the portal loads but the masthead, sidebar, or state components render unstyled as plain HTML
- the login flow redirects to `/oauth2/callback?...error=invalid_scope`
- the Keycloak login form accepts a submit and then renders `We are sorry... Unexpected error when handling authentication request to identity provider.`
- password reset or required-action flows claim success but the reset email never arrives
- `docker compose ps` on `docker-runtime-lv3` shows the `ops-portal` container exited or unhealthy

## Immediate Checks

1. Verify the local runtime on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'docker compose -f /opt/ops-portal/docker-compose.yml ps'
```

2. Verify the local health endpoint:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'curl -sf http://127.0.0.1:8092/health'
```

3. Verify the runtime assurance overview partial still renders:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'curl -sf http://127.0.0.1:8092/partials/overview | grep -F "Runtime Assurance"'
```

4. Verify the edge can still reach the runtime:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.10 \
  'curl -k -I -H "Host: ops.lv3.org" https://127.0.0.1/health'
```

5. If the portal redirects to Keycloak but the submit fails, check the Keycloak runtime directly:

```bash
curl -I https://sso.lv3.org/realms/lv3/.well-known/openid-configuration
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'docker logs --tail 80 keycloak-keycloak-1'
```

If the logs show `Acquisition timeout while waiting for new connection`, the JDBC pool is wedged. If a restart then fails with `No chain/target/match by that name`, Docker's nat chain on `docker-runtime-lv3` is missing and Keycloak must be recreated after Docker itself is restarted.

6. If the shell renders but charts stay blank or the shared PatternFly shell is
   unstyled, verify the same-origin runtime assets and mirrored topology file
   are present inside the container:

```bash
ssh ops@100.118.189.95 'ssh ops@10.10.10.20 "docker exec ops-portal ls /app/ops_portal/static && ls /opt/ops-portal/data/config/dependency-graph.json"'
```

## Recovery

1. Re-apply the portal runtime:

```bash
make converge-ops-portal
```

If a branch-local worktree replay must stay off the protected canonical-truth
path and `make live-apply-service service=ops_portal ...` fails closed before
mutation because it would rewrite `README.md` or `versions/stack.yaml`, use the
governed scoped replay sequence directly and point the runtime sync at the
exact worktree:

```bash
TRACE_ID=$(python3 -c 'import uuid; print(uuid.uuid4().hex)')
RUN_ID="$TRACE_ID"
REPO=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/<worktree>
BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519

export LV3_RUN_ID="$RUN_ID"
export ANSIBLE_LOCAL_TEMP=/tmp/proxmox_florin_server-ansible-local
export ANSIBLE_REMOTE_TEMP=/tmp

uvx --from pyyaml python "$REPO/scripts/interface_contracts.py" --check-live-apply "service:ops_portal"
python3 "$REPO/scripts/promotion_pipeline.py" --emit-bypass-event --service "ops_portal" --actor-id "${USER:-unknown}" --correlation-id "break-glass:service:ops_portal:$(date -u +%Y%m%dT%H%M%SZ)"
uv run --with pyyaml python "$REPO/scripts/standby_capacity.py" --service "ops_portal"
uv run --with pyyaml --with jsonschema python "$REPO/scripts/service_redundancy.py" --check-live-apply --service "ops_portal"
uv run --with pyyaml --with jsonschema python "$REPO/scripts/immutable_guest_replacement.py" --check-live-apply --service "ops_portal" --allow-in-place-mutation
ANSIBLE_HOST_KEY_CHECKING=False "$REPO/scripts/run_with_namespace.sh" uvx --from pyyaml python "$REPO/scripts/ansible_scope_runner.py" run --inventory "$REPO/inventory/hosts.yml" --run-id "$RUN_ID" --playbook "$REPO/playbooks/services/ops_portal.yml" --env production -- --private-key "$BOOTSTRAP_KEY" -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e platform_trace_id="$TRACE_ID" -e bypass_promotion=true -e ops_portal_repo_root="$REPO"
```

Keep the explicit `-e ops_portal_repo_root="$REPO"` override. Without it, the
controller-side sync can read from the top-level checkout instead of the active
worktree and fail on missing live inputs such as `runtime_assurance.py` or
`portal.js`.

The runtime data mirror now syncs only structured production/staging `*.json`
live-apply and drift receipts into `/opt/ops-portal/data/receipts/`. Evidence
transcripts under `receipts/live-applies/evidence/` and preview payloads under
`receipts/live-applies/preview/` stay in the repo for audit history and
non-production validation, but they are intentionally excluded from the guest
sync because the runtime only reads production and staging receipt JSON files.

If a Codex-managed local replay exits with signal `15` before the first remote
task output appears, treat that as a controller-local interruption rather than
proof that the guest apply failed. Move to the staged service/data resync below
instead of assuming the runtime itself rejected the change.

2. If `/health` returns `200` but `/partials/overview` does not include the
   runtime assurance section, treat that as a failed portal converge and replay
   the runtime before trusting the shell.

3. If a replay is interrupted and the guest still serves stale portal sources,
   compare the repo hashes with the guest-local runtime and then resync the
   exact service payload through a temporary directory before rebuilding. If
   `/opt/ops-portal/docker-compose.yml` already points at
   `/opt/ops-portal/build-context`, compare and refresh both the service tree
   and the mirrored build context:

```bash
sha256sum scripts/ops_portal/app.py scripts/ops_portal/templates/partials/overview.html \
  scripts/ops_portal/static/portal.css scripts/ops_portal/static/portal.js

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'sha256sum /opt/ops-portal/service/ops_portal/app.py /opt/ops-portal/service/ops_portal/templates/partials/overview.html /opt/ops-portal/service/ops_portal/static/portal.css /opt/ops-portal/service/ops_portal/static/portal.js /opt/ops-portal/build-context/ops_portal/app.py /opt/ops-portal/build-context/ops_portal/templates/partials/overview.html /opt/ops-portal/build-context/ops_portal/static/portal.css /opt/ops-portal/build-context/ops_portal/static/portal.js'

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'rm -rf /tmp/ops-portal-replay && mkdir -p /tmp/ops-portal-replay'

scp -r \
  -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  scripts/ops_portal scripts/search_fabric scripts/publication_contract.py \
  ops@10.10.10.20:/tmp/ops-portal-replay/

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'sudo rm -rf /opt/ops-portal/service/ops_portal /opt/ops-portal/service/search_fabric /opt/ops-portal/service/publication_contract.py /opt/ops-portal/service/requirements.txt \
   && sudo mkdir -p /opt/ops-portal/service \
   && sudo cp -R /tmp/ops-portal-replay/ops_portal /opt/ops-portal/service/ops_portal \
   && sudo cp -R /tmp/ops-portal-replay/search_fabric /opt/ops-portal/service/search_fabric \
   && sudo cp /tmp/ops-portal-replay/publication_contract.py /opt/ops-portal/service/publication_contract.py \
   && sudo find /opt/ops-portal/data -name "._*" -delete'

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'sudo install -m 0644 /dev/stdin /opt/ops-portal/service/requirements.txt' \
  < requirements/ops-portal.txt

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'sudo rm -rf /opt/ops-portal/build-context/ops_portal /opt/ops-portal/build-context/search_fabric /opt/ops-portal/build-context/publication_contract.py /opt/ops-portal/build-context/requirements.txt /opt/ops-portal/build-context/Dockerfile \
   && sudo mkdir -p /opt/ops-portal/build-context \
   && sudo cp -R /opt/ops-portal/service/ops_portal /opt/ops-portal/build-context/ops_portal \
   && sudo cp -R /opt/ops-portal/service/search_fabric /opt/ops-portal/build-context/search_fabric \
   && sudo cp /opt/ops-portal/service/publication_contract.py /opt/ops-portal/build-context/publication_contract.py \
   && sudo cp /opt/ops-portal/service/requirements.txt /opt/ops-portal/build-context/requirements.txt \
   && sudo cp /opt/ops-portal/service/Dockerfile /opt/ops-portal/build-context/Dockerfile \
   && grep -F "context: /opt/ops-portal/build-context" /opt/ops-portal/docker-compose.yml'

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'cd /opt/ops-portal && sudo docker compose up -d --build --remove-orphans'
```

4. If the runtime is healthy locally but the public hostname fails, re-apply the
   edge. For branch-local replays, keep the contract gate on
   `service:public-edge` and then call the service playbook directly because
   `standby_capacity.py`, `service_redundancy.py`, and
   `immutable_guest_replacement.py` do not catalogue `public-edge`:

```bash
TRACE_ID=$(python3 -c 'import uuid; print(uuid.uuid4().hex)')
RUN_ID="$TRACE_ID"
REPO=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.worktrees/<worktree>
BOOTSTRAP_KEY=/Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519

export LV3_RUN_ID="$RUN_ID"
export ANSIBLE_LOCAL_TEMP=/tmp/proxmox_florin_server-ansible-local
export ANSIBLE_REMOTE_TEMP=/tmp

uvx --from pyyaml python "$REPO/scripts/interface_contracts.py" --check-live-apply "service:public-edge"
python3 "$REPO/scripts/promotion_pipeline.py" --emit-bypass-event --service "public-edge" --actor-id "${USER:-unknown}" --correlation-id "break-glass:service:public-edge:$(date -u +%Y%m%dT%H%M%SZ)"
ANSIBLE_HOST_KEY_CHECKING=False "$REPO/scripts/run_with_namespace.sh" uvx --from pyyaml python "$REPO/scripts/ansible_scope_runner.py" run --inventory "$REPO/inventory/hosts.yml" --run-id "$RUN_ID" --playbook "$REPO/playbooks/services/public-edge.yml" --env production -- --private-key "$BOOTSTRAP_KEY" -e proxmox_guest_ssh_connection_mode=proxmox_host_jump -e platform_trace_id="$TRACE_ID" -e bypass_promotion=true
```

5. If gateway-backed actions fail while the UI shell loads, confirm the configured `GATEWAY_URL` from `/opt/ops-portal/ops-portal.env` and verify the API gateway separately before restarting the portal.

6. If the portal shell loads but the publication badges are missing or stale,
   confirm `/opt/ops-portal/data/config/subdomain-exposure-registry.json` was
   updated with the current repo commit before rebuilding the runtime.

7. If the chart panels are blank but the shell loads, confirm both
   `/app/ops_portal/static/portal.js` and
   `/opt/ops-portal/data/config/dependency-graph.json` exist inside the running
   container, then re-apply the portal runtime so the mirrored data and assets
   are rebuilt together.

8. If the shared PatternFly shell is unstyled or the mobile navigation drawer
   stops responding, verify the published CSP still allows the pinned
   `https://unpkg.com/@patternfly/patternfly@5.4.0/patternfly.min.css` asset
   and that `/static/portal.js` loads from the same origin.

9. If the callback includes `error=invalid_scope`, verify the rendered oauth2-proxy config on `nginx-lv3` does not request a custom `groups` scope. The portal relies on a client-mapped `groups` claim, so the requested scope must stay `openid profile email` unless a real Keycloak client scope named `groups` is added and assigned.
10. If the auth failure is actually Keycloak, recover the runtime from the Proxmox host through the guest agent:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  root@100.64.0.1 \
  "qm guest exec 120 -- /bin/sh -lc 'systemctl restart docker'"

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  root@100.64.0.1 \
  \"qm guest exec 120 -- /bin/sh -lc 'cd /opt/keycloak && docker compose up -d --force-recreate keycloak'\"
```

11. Re-verify the IdP and portal redirect path:

```bash
curl -I https://sso.lv3.org/realms/lv3/.well-known/openid-configuration
curl -I https://ops.lv3.org/oauth2/sign_in
```

12. If login is healthy but password-reset mail is still broken, verify the realm SMTP path and the private relay on `docker-runtime-lv3`:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'python3 - <<'"'"'PY'"'"'\nimport smtplib\nfrom pathlib import Path\npassword = Path("/etc/lv3/mail-platform/server-mailbox-password").read_text().strip()\nclient = smtplib.SMTP("10.10.10.20", 1587, timeout=10)\nclient.ehlo()\nprint(client.login("server", password))\nclient.quit()\nPY'

ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ProxyCommand='ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'docker logs --tail 120 keycloak-keycloak-1 | grep -i -E "smtp|reset_password|required.action"'
```

Use the base login URLs (`https://ops.lv3.org` or `https://ops.lv3.org/oauth2/sign_in`) when retesting. A stale `login-actions/...` or `reset-credentials?...` URL without the matching browser cookie can still render Keycloak's generic `We are sorry...` page even when the live service is healthy.

## Static Fallback

The legacy generated portal landing page is archived at `receipts/ops-portal-snapshot.html`. Use it as a read-only fallback when the interactive runtime is unavailable.
