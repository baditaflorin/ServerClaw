# Configure Runtime-Control Pool

## Purpose

This runbook converges the ADR 0319 and ADR 0320 fixed-capacity control-plane
pool by provisioning `runtime-control`, enrolling it as a Nomad client,
standing up the private Traefik plus Dapr substrate, moving the control-plane
anchors onto it, and retiring the legacy copies from `docker-runtime`.

## Result

- Proxmox guest `runtime-control` exists at `10.10.10.92` with VMID `192`
- `runtime-control` runs Docker, the repo-managed guest firewall, Traefik
  on `9080`, and Dapr on `3500`
- `monitoring` exposes the `runtime-control` Nomad namespace and sees
  `runtime-control` as a client
- the control-plane slice for `api_gateway`, `gitea`, `harbor`, `keycloak`,
  `mail_platform`, `nats_jetstream`, `openbao`, `openfga`, `semaphore`,
  `step_ca`, `temporal`, `vaultwarden`, and `windmill` runs on
  `runtime-control`
- the legacy copies of those services are stopped on `docker-runtime`

## Commands

Syntax-check the pool rollout playbook:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
ANSIBLE_CONFIG=ansible.cfg ansible-playbook --syntax-check -i inventory/hosts.yml playbooks/runtime-control-pool.yml -e env=production
```

Run the guarded production live apply:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=runtime-control-pool env=production EXTRA_ARGS='-e bypass_promotion=true'
```

Replay the playbook directly when investigating the pool in isolation:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/runtime-control-pool.yml \
  --private-key .local/ssh/hetzner_llm_agents_ed25519 \
  -e env=production \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Verification

Verify the runtime-control substrate locally on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.92 \
  'curl -fsS http://127.0.0.1:9080/ping && printf "\n" && curl -fsS http://127.0.0.1:3500/v1.0/metadata'
```

Verify Traefik reaches representative moved services:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.92 \
  'curl -fsS http://127.0.0.1:9080/api-gateway/healthz && printf "\n" && curl -fsS http://127.0.0.1:9080/openfga/healthz && printf "\n" && curl -fsS http://127.0.0.1:9080/windmill/api/version'
```

Verify the Dapr invocation bridge proxies through the runtime-control router:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.92 \
  'curl -fsS --path-as-is http://127.0.0.1:3500/v1.0/invoke/http://127.0.0.1:9080/method/openfga/healthz'
```

Verify Nomad sees the runtime-control namespace and client:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml monitoring -m shell \
  -a 'sudo /usr/local/bin/lv3-nomad namespace status runtime-control && sudo /usr/local/bin/lv3-nomad node status | grep -F runtime-control' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify representative private proxies still answer through the Proxmox host:

```bash
curl -fsS http://100.64.0.1:3009/api/healthz
curl -fsS http://100.64.0.1:8014/healthz -H "Authorization: Bearer $(cat /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/openfga/preshared-key.txt)"
curl -fsS https://100.64.0.1:9443/health --cacert /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/step-ca/certs/root_ca.crt
```

OpenBao is intentionally exposed as an mTLS-only private proxy on
`https://100.64.0.1:8200`, so do not treat a bare `curl --cacert ...` request
as a valid verification step here. Reuse the controller-side client-certificate
verification documented in [Configure OpenBao](./configure-openbao.md).

Verify the legacy control-plane copies are no longer running on
`docker-runtime`:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime -m shell \
  -a '! sudo docker ps --format "{{.Names}}" | grep -E "^(gitea|keycloak|openbao|openfga|semaphore|vaultwarden|windmill)$"' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox-host_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Operating Notes

- `runtime-control` is the fixed-capacity control-plane pool. Do not place
  bursty or exploratory workloads there; use `runtime-general` or
  `runtime-ai` instead.
- The pool live apply intentionally replays `lv3.platform.proxmox_network` on
  the host and `lv3.platform.linux_guest_firewall` on `monitoring` because
  the Nomad scheduler and host proxy catalog must learn about the new guest
  before the control-plane services move.
- The dedicated `runtime-control` substrate replay now keeps an already
  running Docker daemon online during the initial guest firewall converge and
  relies on bounded bridge-chain recovery inside
  `lv3.platform.linux_guest_firewall`. Treat an unexpected mid-run
  `systemctl stop docker.service docker.socket` on this guest as drift from an
  older checkout, not expected pool behavior.
- The legacy-retirement phase now fails closed unless the same playbook run has
  already verified the `runtime-control` routes. Do not bypass that guard
  with `--start-at-task`, `--limit docker-runtime`, or ad hoc
  retirement-only replays.
- If the replay stalls while OpenBao configures the PostgreSQL dynamic
  credential backend, verify the live Proxmox guest firewall has actually
  replayed the repo policy for `postgres`. A stale `/etc/pve/firewall/150.fw`
  can still block `10.10.10.92 -> 10.10.10.50:5432` even when
  `inventory/host_vars/proxmox-host.yml` already declares the allowance; in
  that case, re-run `lv3.platform.proxmox_network` on `proxmox-host` before
  retrying the full `runtime-control-pool` play.
- Public edge publications for `api.example.com`, `registry.example.com`, and
  `sso.example.com` still terminate on `nginx-edge`; the runtime-control substrate
  remains private-only.
- `runtime-control` is deliberately excluded from first-phase autoscaling. Its
  memory envelope is governed by ADR 0321, but scaling remains manual until the
  anchor services are stable on the dedicated pool.
