# Configure Nomad

## Purpose

This runbook converges the private Nomad scheduler defined by ADR 0232 for
durable batch jobs and long-running internal services.

It covers:

- controller-local TLS and ACL bootstrap artifacts under `.local/nomad/`
- a single private Nomad server on `monitoring`
- Nomad clients on `docker-runtime`, `runtime-general`, `runtime-ai`, `runtime-control`, and `docker-build`
- a Proxmox-host Tailscale TCP proxy for private controller access
- dedicated `runtime-general`, `runtime-ai`, and `runtime-control` namespaces for the first pool-scoped scheduling boundaries
- repo-managed smoke jobs that verify both long-running service placement and
  dispatchable batch execution

## Preconditions

Before running the workflow, confirm:

1. the controller has the SSH key at `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519`
2. `monitoring`, `docker-runtime`, `runtime-general`, `runtime-ai`, `runtime-control`, and `docker-build` are reachable through the Proxmox jump path
3. the Proxmox host is reachable on its Tailscale address `100.64.0.1`
4. the local workstation can write controller-local bootstrap artifacts under `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/`

## Entrypoints

- syntax check: `make syntax-check-nomad`
- direct converge: `make converge-nomad`
- immutable replacement plan: `make immutable-guest-replacement-plan service=nomad`
- guarded live apply: `make live-apply-service service=nomad env=production`
- documented in-place exception: `make live-apply-service service=nomad env=production ALLOW_IN_PLACE_MUTATION=true`

## Delivered Surfaces

The workflow manages these live surfaces:

- Nomad server on `monitoring` listening on private ports `4646`, `4647`, and `4648`
- Nomad clients on `docker-runtime`, `runtime-general`, `runtime-ai`, `runtime-control`, and `docker-build` with the Docker driver enabled
- dedicated `runtime-general`, `runtime-ai`, and `runtime-control` namespaces for pool-scoped workloads
- controller access to the Nomad API at `https://100.64.0.1:8013`
- mirrored bootstrap management token at `/etc/lv3/nomad/bootstrap-management.token` on `monitoring`
- repo-managed smoke job specs under `/etc/lv3/nomad/jobs/`
- long-running smoke service job `lv3-nomad-smoke-service`
- dispatchable smoke batch job `lv3-nomad-smoke-batch`

## Generated Local Artifacts

After a successful converge, these controller-local files should exist:

- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/tls/nomad-agent-ca.pem`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/tls/server.pem`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/tls/server-key.pem`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/tls/client.pem`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/tls/client-key.pem`
- `/Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/tokens/bootstrap-management.token`

## Verification

Run these checks after converge or after the guarded live apply:

1. `make syntax-check-nomad`
2. `make immutable-guest-replacement-plan service=nomad`
3. `curl -sS https://100.64.0.1:8013/v1/status/leader --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/tls/nomad-agent-ca.pem -H "X-Nomad-Token: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/tokens/bootstrap-management.token)"`
4. `curl -sS https://100.64.0.1:8013/v1/nodes --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/tls/nomad-agent-ca.pem -H "X-Nomad-Token: $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/nomad/tokens/bootstrap-management.token)" | jq -r '.[] | "\(.Name)\t\(.Status)\t\(.NodeClass)"'`
5. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml monitoring -m shell -a 'sudo /usr/local/bin/lv3-nomad namespace status runtime-general' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
6. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml monitoring -m shell -a 'sudo /usr/local/bin/lv3-nomad namespace status runtime-ai' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
7. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml monitoring -m shell -a 'sudo /usr/local/bin/lv3-nomad namespace status runtime-control' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
8. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml monitoring -m shell -a 'sudo systemctl is-active lv3-nomad && sudo /usr/local/bin/lv3-nomad job status lv3-nomad-smoke-service' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
9. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-build -m shell -a 'systemctl is-active lv3-nomad && curl -fsS http://10.10.10.30:18180/' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
10. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime -m shell -a 'systemctl is-active lv3-nomad && sudo cat /var/lib/nomad/verification/lv3-nomad-smoke-batch/last-run.log' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
11. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml runtime-general -m shell -a 'systemctl is-active lv3-nomad && sudo /usr/local/bin/lv3-nomad node status -self | grep -F runtime-general' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
12. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml runtime-ai -m shell -a 'systemctl is-active lv3-nomad && sudo /usr/local/bin/lv3-nomad node status -self | grep -F runtime-ai' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
13. `ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml runtime-control -m shell -a 'systemctl is-active lv3-nomad && sudo /usr/local/bin/lv3-nomad node status -self | grep -F runtime-control' --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 -e proxmox_guest_ssh_connection_mode=proxmox_host_jump`
14. `make live-apply-service service=nomad env=production`
15. `make live-apply-service service=nomad env=production ALLOW_IN_PLACE_MUTATION=true`

## OIDC Authentication (ADR 0361)

The Nomad UI at `https://scheduler.example.com` uses Nomad's native OIDC auth method
backed by Keycloak. No oauth2-proxy is used — Nomad handles login directly.

### How it works

1. User opens `https://scheduler.example.com`
2. Nomad UI shows "Sign In with OIDC" button
3. Click redirects to Keycloak (`sso.example.com`) for authentication
4. On success, Nomad exchanges the OIDC token for a Nomad ACL token
5. Token is stored in the browser; user can view/manage jobs

### Access levels

- **lv3-platform-admins** Keycloak group → `platform-admin` role (full write)
- All other authenticated users → `platform-reader` role (read-only)

### Converging OIDC auth

```bash
# Run the OIDC-specific tier only:
make converge-nomad  # or with tags:
ansible-playbook playbooks/nomad.yml --tags service-nomad-oidc -e env=production
```

### Verifying OIDC

```bash
# Check auth method exists:
curl -sS https://100.64.0.1:8013/v1/acl/auth-method/keycloak \
  --cacert .local/nomad/tls/nomad-agent-ca.pem \
  -H "X-Nomad-Token: $(cat .local/nomad/tokens/bootstrap-management.token)" | jq .Name

# List binding rules:
curl -sS https://100.64.0.1:8013/v1/acl/binding-rules \
  --cacert .local/nomad/tls/nomad-agent-ca.pem \
  -H "X-Nomad-Token: $(cat .local/nomad/tokens/bootstrap-management.token)" | jq '.[] | {AuthMethod, BindName, Selector}'
```

## Notes

- The Nomad UI is edge-published at `scheduler.example.com` with OIDC auth (ADR 0361). The Tailscale proxy at `100.64.0.1:8013` remains available for API-level access with the management token.
- The `lv3-nomad` systemd unit intentionally runs as `root` so the agent can read the root-owned TLS key and use the Docker driver reliably on the client nodes.
- The controller-local bootstrap token is the branch-safe source of truth; if the local token is missing but the mirrored server token still exists, rerun the playbook to restore it automatically.
- The smoke service is pinned to the build client and is verified through the build node's advertised address `10.10.10.30:18180`, not `127.0.0.1`.
- The dispatchable batch smoke job is pinned to the runtime client and writes a durable verification marker to `/var/lib/nomad/verification/lv3-nomad-smoke-batch/last-run.log` so the post-dispatch proof does not depend on ephemeral allocation log state.
- The `runtime-general`, `runtime-ai`, and `runtime-control` namespaces are the first pool-scoped scheduler boundaries introduced by ADR 0319 and ADR 0320. Keep support surfaces, AI-bursty jobs, and control-plane anchors there instead of reusing the broad `default` namespace.
- Because `nomad` is hosted on `monitoring`, the guarded production entrypoint is governed by ADR 0191 immutable guest replacement. The default `make live-apply-service service=nomad env=production` path therefore fails closed until an immutable replacement plan is used or a documented narrow exception is acknowledged with `ALLOW_IN_PLACE_MUTATION=true`.
