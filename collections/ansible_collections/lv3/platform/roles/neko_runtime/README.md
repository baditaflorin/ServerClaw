# neko_runtime

Deploy Neko remote desktop for interactive operator browser access via WebRTC.

## Description

Neko (`m1k1o/neko`) provides a web-based remote desktop interface streamed via WebRTC to operator browsers. This role:

- Pulls and runs the Neko Docker image
- Configures signalling endpoint (TCP 8080, proxied via NGINX at `browser.lv3.org`)
- Enables WebRTC media streams (UDP RTP on 50000–60000 range)
- Provides health checks and verification testing

This role is typically deployed on a dedicated VM (`runtime-comms-lv3`, VMID 121) to prevent resource contention with other real-time services per ADR 0347.

## Role Variables

See `meta/argument_specs.yml` for formal argument validation.

### Required

- **None.** All variables have sensible defaults.

### Optional

- `neko_runtime_image_tag` (default: `"3.x"`) – Docker image tag/version for m1k1o/neko
- `neko_runtime_container_name` (default: `"neko"`) – Container name
- `neko_runtime_port` (default: `8080`) – TCP port for signalling
- `neko_runtime_data_dir` (default: `"/opt/neko"`) – Persistent storage directory (logs, cache, config)
- `neko_runtime_browser` (default: `"chromium"`) – Browser engine ("chromium" or "firefox")
- `neko_runtime_res` (default: `"1440x900"`) – Display resolution as "WIDTHxHEIGHT"
- `neko_runtime_max_connections` (default: `1`) – Maximum concurrent operator sessions
- `neko_runtime_password` (default: `""`) – Optional WebRTC session password (empty = no auth)

## Role Tags

- `tier-1`: Service deployment (converge role)
- `automation`: Service lifecycle management
- `service-neko`: Neko-specific tasks

## Dependencies

- `lv3.platform.common` – Shared infrastructure (directory creation, Docker daemon)
- `lv3.platform.docker_runtime` – Docker installation and daemon configuration
- `lv3.platform.linux_guest_firewall` – Guest-level nftables policy (if network isolation needed)

## Handlers

- `restart neko` – Restart Neko container (triggered by configuration changes)

## Example Usage

Minimal playbook:

```yaml
- hosts: runtime-comms-lv3
  become: true
  gather_facts: true
  roles:
    - role: lv3.platform.common
    - role: lv3.platform.docker_runtime
    - role: lv3.platform.neko_runtime
```

With custom image and resolution:

```yaml
- hosts: runtime-comms-lv3
  become: true
  gather_facts: true
  roles:
    - role: lv3.platform.neko_runtime
      vars:
        neko_runtime_image_tag: "3.2"
        neko_runtime_res: "2560x1440"
        neko_runtime_browser: "firefox"
```

## Verification

The role includes two verification strategies:

### Health Check (Local)

```bash
curl -fs http://127.0.0.1:8080/api/health
# Returns: {"ok":true} with HTTP 200
```

### WebRTC Handshake Test (Synthetic)

```bash
python3 scripts/verify_neko_webrtc_session.py \
  --url localhost:8080 \
  --timeout 30
# Verifies WebSocket handshake + SDP offer/answer exchange
```

## Architecture

### Signalling Path (TCP WebSocket → NGINX)

```
Operator browser
       ↓
nginx-lv3 (TLS termination)
       ↓
proxy pass → runtime-comms-lv3:8080 (Neko signalling)
```

### Media Path (UDP RTP → Direct from Host)

```
Neko container (UDP 50000–60000)
       ↓
Proxmox host port forwarding (proxmox_florin.yml)
       ↓
Operator network (Tailscale 100.64.0.0/10)
```

This split prevents media latency (TLS decryption/re-encryption via NGINX would add jitter).

See ADR 0380 for full architecture and rationale.

## Troubleshooting

### Container fails to start

Check Docker logs:

```bash
docker logs neko
```

Common issues:
- Display server configuration (DISPLAY env var)
- Browser binary not found (firefox/chromium not installed in image)
- Insufficient memory (Chromium rendering requires 1–2 GB)

### WebRTC negotiation times out

Verify firewall rules allow UDP media:

```bash
sudo nft list ruleset | grep -E "50000|60000"
```

Expected: Rules forwarding UDP 50000–60000 from public interface to container IP.

### Connection drops after 60 seconds

Verify NGINX proxy timeout is set correctly:

```bash
grep proxy_read_timeout /etc/nginx/sites-enabled/browser.lv3.org.conf
# Should output: proxy_read_timeout 3600s;
```

See ADR 0170 exception in ADR 0380 for rationale.

## References

- **Neko Project:** https://github.com/m1k1o/neko
- **ADR 0293:** LiveKit remote communication (reference WebRTC deployment)
- **ADR 0347:** Docker runtime workload split (why separate VM)
- **ADR 0380:** Neko architecture decision (full context & testing strategy)
