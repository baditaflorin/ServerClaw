# Configure Runtime-AI Pool

## Purpose

This runbook converges the first ADR 0319 and ADR 0320 production pool split by
provisioning `runtime-ai-lv3`, enrolling it as a Nomad client, standing up the
Traefik plus Dapr substrate, and moving the initial document-extraction slice
off `docker-runtime-lv3`.

## Result

- Proxmox guest `runtime-ai-lv3` exists at `10.10.10.90` with VMID `190`
- `runtime-ai-lv3` runs Docker, the repo-managed guest firewall, Traefik on `9080`, and Dapr on `3500`
- `monitoring-lv3` exposes the `runtime-ai` Nomad namespace and sees `runtime-ai-lv3` as a client
- Apache Tika, Gotenberg, and Tesseract OCR run privately on `runtime-ai-lv3`
- the legacy Tika, Gotenberg, and Tesseract OCR copies are stopped on `docker-runtime-lv3`
- the shared API gateway continues to proxy `/v1/gotenberg` to the new runtime-ai upstream
- the Proxmox host firewall is replayed as part of the same live apply so `runtime-ai-lv3` and the existing guests receive the new east-west rules in the same transaction
- the monitoring guest-side nftables policy is replayed in the same run so the Nomad scheduler actually admits the new `runtime-ai-lv3` traffic paths after the host firewall changes without replaying the fragile shared runtime firewall state
- if that monitoring replay temporarily drops Docker bridge chains, the role is allowed one bounded Docker restart on `monitoring-lv3` to restore them before the play continues

## Commands

Syntax-check the pool rollout playbook:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ANSIBLE_CONFIG=ansible.cfg ansible-playbook --syntax-check -i inventory/hosts.yml playbooks/runtime-ai-pool.yml -e env=production
```

Run the guarded production live apply:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=runtime-ai-pool env=production EXTRA_ARGS='-e bypass_promotion=true'
```

Replay the playbook directly when investigating the pool in isolation:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i inventory/hosts.yml playbooks/runtime-ai-pool.yml \
  --private-key .local/ssh/hetzner_llm_agents_ed25519 \
  -e env=production \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

## Verification

Verify the runtime-ai substrate locally on the guest:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.90 \
  'curl -fsS http://127.0.0.1:9080/ping && printf "\n" && curl -fsS http://127.0.0.1:3500/v1.0/metadata'
```

Verify Traefik reaches the three migrated services:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.90 \
  'curl -fsS http://127.0.0.1:9080/tika/version && printf "\n" && curl -fsS http://127.0.0.1:9080/gotenberg/health && printf "\n" && curl -fsS http://127.0.0.1:9080/tesseract-ocr/healthz'
```

Verify the Dapr invocation bridge proxies through the runtime-ai router:

```bash
ssh -i /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -J ops@100.64.0.1 \
  ops@10.10.10.90 \
  'curl -fsS --path-as-is http://127.0.0.1:3500/v1.0/invoke/http://127.0.0.1:9080/method/tika/version'
```

Verify Nomad sees the runtime-ai namespace and client:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml monitoring-lv3 -m shell \
  -a 'sudo /usr/local/bin/lv3-nomad namespace status runtime-ai && sudo /usr/local/bin/lv3-nomad node status | grep -F runtime-ai-lv3' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the legacy document-extraction copies are no longer running on `docker-runtime-lv3`:

```bash
ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime-lv3 -m shell \
  -a '! sudo docker ps --format "{{.Names}}" | grep -E "^(gotenberg|tika|tesseract-ocr)$"' \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Verify the shared API gateway still serves the authenticated Gotenberg route:

```bash
cd /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server
LV3_TOKEN="$(cat .local/platform-context/api-token.txt)"
curl -fsS -H "Authorization: Bearer $LV3_TOKEN" https://api.lv3.org/v1/gotenberg/health
```

## Operating Notes

- This pool is the first production slice, not the final partitioning end state. Keep the moved services limited to the document-extraction boundary until follow-on pools are planned.
- The current Proxmox host only exposes the base template VM `9000`, so `runtime-ai-lv3` clones from `lv3-debian-base` and the playbook's `docker_runtime` role installs Docker during first converge. Do not switch this guest back to `lv3-docker-host` until the richer template is rebuilt and applied live.
- The pool live apply now replays `lv3.platform.proxmox_network` on the host after provisioning `runtime-ai-lv3`. Keep that host-side step in place because the Nomad scheduler and other existing guests need their Proxmox VM firewall files refreshed whenever a new pool guest appears.
- The pool live apply also replays `lv3.platform.linux_guest_firewall` on `monitoring-lv3` after the new guest appears. Keep that targeted guest-side replay in place so the Nomad scheduler admits `runtime-ai-lv3`, but do not broaden it back to the entire guest set unless the shared-runtime Docker bridge behavior is hardened first.
- The `monitoring-lv3` replay opts into bounded Docker bridge-chain recovery inside `lv3.platform.linux_guest_firewall`. That recovery is intentionally scoped to the monitoring guest for this ADR and is not the green light to auto-restart Docker on the shared runtime.
- Traefik and Dapr on `runtime-ai-lv3` are private infrastructure surfaces. Do not publish them directly on the public edge.
- Dapr service invocation reaches the local router through the direct non-Dapr endpoint URL form (`/v1.0/invoke/http://127.0.0.1:9080/...`), not through self-discovery on the `runtime-ai-router` app id. Keep `curl --path-as-is` in operator checks so the nested `http://` path is preserved verbatim.
- The legacy-retirement play on `docker-runtime-lv3` intentionally stops only the old Tika, Gotenberg, and Tesseract compose stacks. It does not replay the shared runtime's firewall or Docker baseline roles, because that cleanup step should not mutate the entire shared pool just to remove three superseded services.
- The legacy-retirement phase now fails closed unless the same playbook run has already verified the `runtime-ai-lv3` routes. Do not bypass that guard with `--start-at-task`, `--limit docker-runtime-lv3`, or ad hoc retirement-only replays.
- `runtime-ai-lv3` is the supported place for memory-bursty document extraction and similar AI-adjacent helpers. Do not reintroduce these workloads on `docker-runtime-lv3` without a new ADR or rollback decision.
- The shared API gateway still runs on `docker-runtime-lv3`. The pool playbook refreshes it after the upstream move so `/v1/gotenberg` keeps working.
