# Configure Open WebUI

## Purpose

This runbook converges the private Open WebUI operator-and-agent workbench defined by ADR 0060.

## Result

- `docker-runtime-lv3` runs Open WebUI from `/opt/open-webui`
- the Proxmox host publishes an operator-only Tailscale TCP proxy at `http://100.118.189.95:8008`
- controller-local bootstrap secrets are mirrored under `.local/open-webui/`
- repo-managed environment settings disable public signup, community sharing, and unapproved connector drift by default
- future Keycloak OIDC can be enabled without changing the deployment shape

## Controller-Local Inputs

Generated automatically on first converge:

- `.local/open-webui/admin-password.txt`
- `.local/open-webui/webui-secret-key.txt`

Optional external inputs for stricter production use:

- `.local/open-webui/provider.env`
  - include only approved connector variables such as `OPENAI_API_KEY`, `OPENAI_API_BASE_URL`, `DEFAULT_MODELS`, and `DEFAULT_PINNED_MODELS`
  - keep this file local-only and do not commit it
- `.local/open-webui/oidc-client-secret.txt`
  - only needed when enabling Keycloak-backed OIDC later

Example `provider.env`:

```dotenv
ENABLE_OPENAI_API=True
OPENAI_API_KEY=...
OPENAI_API_BASE_URL=https://api.openai.com/v1
DEFAULT_MODELS=gpt-4.1
DEFAULT_PINNED_MODELS=gpt-4.1
```

## Commands

Syntax-check the Open WebUI workflow:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make syntax-check-open-webui
```

Converge the private runtime and host-side Tailscale proxy:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
make converge-open-webui
```

## Verification

Verify the runtime container and local files on `docker-runtime-lv3`:

```bash
ansible -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/inventory/hosts.yml docker-runtime-lv3 -m shell -a 'docker compose --env-file /opt/open-webui/open-webui.env --file /opt/open-webui/docker-compose.yml ps && sudo ls -ld /opt/open-webui /opt/open-webui/data /etc/lv3/open-webui' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the private operator entrypoint is reachable:

```bash
curl -I http://100.118.189.95:8008/
```

Verify the bootstrap admin can sign in:

```bash
curl -s -X POST http://100.118.189.95:8008/api/v1/auths/signin \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"ops@lv3.org\",\"password\":\"$(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/open-webui/admin-password.txt)\"}"
```

## Operating Notes

- Keep `ENABLE_PERSISTENT_CONFIG=False` so repo-managed environment values remain authoritative across restarts.
- Treat `.local/open-webui/` as sensitive controller-only material.
- Do not enable arbitrary outbound connectors in the UI. Add approved connector settings through `.local/open-webui/provider.env` and rerun the workflow.
- Keep password auth enabled until ADR 0056 is live and the OIDC client values are ready. This role already supports the future switch.
- The first rollout is intentionally read-heavy. Governed tool registration and repo-grounded RAG belong to ADR 0069 and ADR 0070 instead of being hidden inside this runtime.
