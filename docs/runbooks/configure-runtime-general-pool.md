# Configure Runtime-General Pool

## Purpose

This runbook converges the follow-on ADR 0319 and ADR 0320 production pool
split by provisioning `runtime-general-lv3`, enrolling it as a Nomad client,
standing up the Traefik plus Dapr substrate, and moving the first lightweight
operator and support services off `docker-runtime-lv3`.

## Result

- Proxmox guest `runtime-general-lv3` exists at `10.10.10.91` with VMID `191`
- `runtime-general-lv3` runs Docker, the repo-managed guest firewall, Traefik on `9080`, and Dapr on `3500`
- `monitoring-lv3` exposes the `runtime-general` Nomad namespace and sees `runtime-general-lv3` as a client
- Uptime Kuma, the public status-page backing route, Homepage, and Mailpit run on `runtime-general-lv3`
- the legacy Uptime Kuma, Homepage, and Mailpit copies are stopped on `docker-runtime-lv3`
- the shared NGINX edge continues to publish `uptime.lv3.org`, `status.lv3.org`, and `home.lv3.org` against the new runtime-general upstreams

## Commands

Syntax-check the pool rollout playbook:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ANSIBLE_CONFIG=ansible.cfg ansible-playbook --syntax-check -i inventory/hosts.yml playbooks/runtime-general-pool.yml -e env=production
```

Run the guarded production live apply:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=runtime-general-pool env=production EXTRA_ARGS='-e bypass_promotion=true'
```

Replay the playbook directly when investigating the pool in isolation:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/runtime-general-pool.yml \
  --private-key .local/ssh/hetzner_llm_agents_ed25519 \
  -e env=production \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Verification

Verify the runtime-general substrate locally on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.91 \
  'curl -fsS http://127.0.0.1:9080/ping && printf "\n" && curl -fsS http://127.0.0.1:3500/v1.0/metadata'
```

Verify Traefik reaches the moved services:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.91 \
  'curl -fsS http://127.0.0.1:9080/uptime-kuma && printf "\n" && curl -fsS http://127.0.0.1:9080/homepage && printf "\n" && curl -fsS http://127.0.0.1:9080/mailpit/api/v1/info'
```

Verify the Dapr invocation bridge proxies through the runtime-general router:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.91 \
  'curl -fsS --path-as-is http://127.0.0.1:3500/v1.0/invoke/http://127.0.0.1:9080/method/uptime-kuma'
```

Verify Nomad sees the runtime-general namespace and client:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml monitoring-lv3 -m shell \
  -a 'sudo /usr/local/bin/lv3-nomad namespace status runtime-general && sudo /usr/local/bin/lv3-nomad node status | grep -F runtime-general-lv3' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the shared edge still serves the moved public routes:

```bash
curl -Ik https://uptime.lv3.org
curl -Ik https://status.lv3.org
curl -Ik https://home.lv3.org
```

Verify the legacy support-service copies are no longer running on `docker-runtime-lv3`:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime-lv3 -m shell \
  -a '! sudo docker ps --format "{{.Names}}" | grep -E "^(homepage|mailpit|uptime-kuma)$"' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Operating Notes

- This pool is the first lightweight operator-and-support wave, not the final runtime-general service set. Keep the moved services limited to low-risk observability and operator surfaces until the broader wave is reviewed.
- The current Proxmox host only exposes the base template VM `9000`, so `runtime-general-lv3` clones from `lv3-debian-base` and the playbook's `docker_runtime` role installs Docker during first converge.
- The pool live apply replays `lv3.platform.proxmox_network` on the host after provisioning `runtime-general-lv3`. Keep that host-side step in place because the Nomad scheduler and other existing guests need their Proxmox VM firewall files refreshed whenever a new pool guest appears.
- The dedicated `runtime-general-lv3` substrate replay now keeps an already
  running Docker daemon online during the initial guest firewall converge and
  relies on bounded bridge-chain recovery inside
  `lv3.platform.linux_guest_firewall`. Treat an unexpected mid-run
  `systemctl stop docker.service docker.socket` on this guest as drift from an
  older checkout, not expected pool behavior.
- The pool live apply also replays `lv3.platform.linux_guest_firewall` on `monitoring-lv3` after the new guest appears. Keep that targeted guest-side replay in place so the Nomad scheduler admits `runtime-general-lv3`, but do not broaden it back to the entire guest set unless the shared-runtime Docker bridge behavior is hardened first.
- The first successful runtime-general service replay now restores the legacy `docker-runtime-lv3` Uptime Kuma data directory onto `runtime-general-lv3` before retirement and records `/opt/uptime-kuma/.legacy-data-restored` as the one-time migration marker. If that marker is absent unexpectedly, inspect both guests before forcing another replay.
- The legacy-retirement phase now fails closed unless the same playbook run has already verified the `runtime-general-lv3` routes and the shared edge publication. Do not bypass that guard with `--start-at-task`, `--limit docker-runtime-lv3`, or ad hoc retirement-only replays.
- Homepage now binds both the guest address and loopback on `runtime-general-lv3` so the shared Traefik router can keep using `127.0.0.1:3090` without exposing a second public edge path. If `/homepage` returns `502`, confirm the loopback listener first.
- Traefik and Dapr on `runtime-general-lv3` are private infrastructure surfaces. Do not publish them directly on the public edge.
- `runtime-general-lv3` is the supported place for lightweight operator and support surfaces such as Uptime Kuma, Homepage, and Mailpit. Do not reintroduce these workloads on `docker-runtime-lv3` without a new ADR or rollback decision.
