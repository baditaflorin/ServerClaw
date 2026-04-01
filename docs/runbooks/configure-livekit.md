# Configure LiveKit

This runbook covers the repo-managed LiveKit deployment introduced by
[ADR 0293](../adr/0293-livekit-as-the-real-time-audio-and-voice-channel-for-agents.md).

## Scope

The LiveKit workflow converges:

- the LiveKit server runtime on `docker-runtime-lv3`
- controller-local API credentials mirrored under `.local/livekit/`
- public signalling at `https://livekit.lv3.org` through the shared NGINX edge
- direct public TCP `7881` and UDP `7882` forwarding from the Proxmox host to `docker-runtime-lv3`
- guest-local and public room-lifecycle verification through the repo-managed helper script

## Preconditions

- `bootstrap_ssh_private_key` is present under `.local/ssh/`
- the OpenBao init payload is already available under `.local/openbao/init.json`
- `HETZNER_DNS_API_TOKEN` is available for DNS publication and certificate expansion on the shared edge

## Converge

Run:

```bash
HETZNER_DNS_API_TOKEN=... make converge-livekit
```

The target validates the public subdomain contract and refreshes the shared
edge static artifacts before publishing `livekit.lv3.org`, so a fresh worktree
does not need a separate docs or portal generation step.

## Governed Live Apply

For the governed production service lane, run:

```bash
ALLOW_IN_PLACE_MUTATION=true make live-apply-service service=livekit env=production
```

`docker-runtime-lv3` is governed by ADR 0191 immutable guest replacement, so
the in-place mutation override is a documented narrow exception for this
initial LiveKit rollout and any later exact-main replay must record that
exception in the live-apply receipt.

## Generated Local Artifacts

The workflow maintains controller-local credentials under `.local/livekit/`:

- `api-key.txt`
- `api-secret.txt`

## Verification

Repository and syntax checks:

```bash
make syntax-check-livekit
```

Guest-local and public verification:

```bash
python3 scripts/livekit_tool.py verify-room-lifecycle \
  --url https://livekit.lv3.org \
  --api-key-file .local/livekit/api-key.txt \
  --api-secret-file .local/livekit/api-secret.txt \
  --room-prefix livekit-runbook-verify \
  --identity livekit-runbook-probe \
  --timeout-seconds 120

ANSIBLE_HOST_KEY_CHECKING=False ansible -i inventory/hosts.yml docker-runtime-lv3 \
  -m shell \
  -a "ss -lnt | grep -E ':(7880|7881) ' && ss -lun | grep -E ':(7882) '" \
  --private-key /Users/live/Documents/GITHUB_PROJECTS/proxmox_florin_server/.local/ssh/hetzner_llm_agents_ed25519 \
  -e proxmox_guest_ssh_connection_mode=proxmox_host_jump
```

Expected results:

- the public verification command creates, lists, and deletes a synthetic room
  successfully through `https://livekit.lv3.org`
- `docker-runtime-lv3` shows local listeners on TCP `7880`, TCP `7881`, and UDP
  `7882`
- the Proxmox host forwards public TCP `7881` and UDP `7882` to
  `10.10.10.20`

## Notes

- `livekit.lv3.org` is intentionally governed by upstream-issued LiveKit
  tokens rather than the shared edge OIDC boundary
- signalling is proxied through the shared NGINX edge, but media TCP and UDP
  listeners are forwarded directly by the Proxmox host to keep WebRTC media
  transport outside the TLS-terminating proxy hop
- if the controller-local API credentials are lost, delete
  `.local/livekit/api-key.txt` and `.local/livekit/api-secret.txt` and rerun
  `make converge-livekit` from the current repo state
