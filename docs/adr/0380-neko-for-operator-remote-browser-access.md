# ADR 0380: Neko Remote Desktop for Interactive Operator Browser Access

**Status:** Accepted

**Date:** 2026-04-06

**Context:**

The platform currently deploys **headless browser automation** (Playwright browser-runner at `http://10.10.10.20:8096/`) for structured, programmatic testing and data collection workflows. This service is fundamentally non-interactive: it executes predefined scripts via HTTP APIs.

However, operators frequently require **interactive browser debugging and exploration**—scenarios where:
- Real-time manual testing of complex user flows
- Interactive debugging of third-party OAuth/SAML integrations
- Visual inspection of web application behavior under load
- Ad-hoc troubleshooting without scripting

Previously, such tasks required VPN access or SSH port-forwarding to graphical desktops, creating operational friction and security surface area.

**WebRTC as Access Method:**

Neko (`m1k1o/neko`) is a web-based remote desktop that streams a real browser session via WebRTC. This provides:
- Browser-based access via TLS-secured HTTPS gateway (no VPN client required)
- Bi-directional control: operator keyboard/mouse → browser rendering
- Real-time WebRTC media streaming (UDP RTP) for sub-second latency
- Access restricted to management network (Tailscale `100.64.0.0/10`)

**Past RTC Failures (Context for Architecture):**

Prior WebRTC implementations in this codebase experienced three categories of failure:

1. **Firewall Rule Concurrency Clobbering (commit 17bc4ff5e):**
   - LiveKit UDP media port forwarding rules were erased when concurrent Ansible workstreams applied firewall policy on sibling VMs
   - Root cause: Single shared firewall rule index without per-service locking
   - Symptom: Media streams would work initially, then fail after unrelated infrastructure changes

2. **Timeout Hierarchy Violations:**
   - WebRTC signalling (WebSocket upgrades) and media streams require long-lived connections (15–3600 seconds)
   - Platform's default ADR 0170 timeout hierarchy imposed 60s max on HTTP request layer, breaking long-lived NGINX proxies
   - Symptom: WebRTC connections would drop after 60 seconds without explicit exception

3. **Resource Contention on Shared Docker Runtime:**
   - LiveKit on `docker-runtime-lv3` competes for kernel I/O with Redpanda, Kafka, and Docker registry
   - Real-time media streaming is I/O-sensitive; competing workloads cause packet loss and jitter
   - ADR 0347 documented this as requiring workload isolation but was not retroactively applied to LiveKit
   - Symptom: WebRTC latency spikes during concurrent container deployments

**Decision:**

Deploy Neko remote desktop for interactive operator access on a **dedicated compute VM (runtime-comms-lv3, VMID 121)** with explicit architecture to prevent all three categories of failure:

1. **Dedicated VM (Resource Isolation):**
   - New VM: `runtime-comms-lv3` (VMID 121), `10.10.10.41` (guest network)
   - Sizing: 8 vCPU, 16 GB RAM, 64 GB disk (browser rendering + WebRTC bitrate buffer)
   - OS: Ubuntu 24.04 LTS with cloud-init bootstrap
   - Isolation rationale: Prevents Neko I/O from starving Redpanda/Kafka on docker-runtime-lv3 (applies ADR 0347 lesson learned)

2. **Signalling Path (WebSocket through NGINX):**
   - Protocol: WebSocket upgrade over HTTPS (TLS termination at nginx-lv3)
   - Hostname: `browser.lv3.org`
   - Backend: HTTP proxy to `runtime-comms-lv3:8080` (Neko signalling port)
   - Timeout exception: `proxy_read_timeout 3600s` (documented deviation from ADR 0170 60s constraint)
   - Justification: WebRTC sessions sustain 5–60 minute operator interactions; 60s timeout incompatible with real-world use

3. **Media Path (Direct UDP from Proxmox Host):**
   - Neko exports UDP media streams (RTP/STUN) on port range `50000–60000`
   - Host-level port forwarding: `proxmox_florin` forwards incoming UDP `50000–60000` → `runtime-comms-lv3:50000–60000`
   - Rationale: UDP cannot be proxied through NGINX (no Layer 4 routing); direct forwarding minimizes latency
   - This matches LiveKit architecture (ADR 0293): signalling through TLS proxy, media direct from host

4. **Firewall Locking (Concurrency Prevention):**
   - Guest firewall rules for `runtime-comms-lv3` are independent from Docker runtime firewall rules (separate nftables state files)
   - File-level locking in `platform/locking/file_domain.py` (ADR 0153) ensures concurrent Ansible workstreams do not corrupt firewall indexes
   - Consequence: Firewall convergence for `runtime-comms-lv3` cannot race with `docker-runtime-lv3` updates

5. **Network Security:**
   - Inbound traffic restricted to management network:
     - Management SSH (port 22) from Proxmox control plane
     - NGINX edge proxy (port 8080 TCP) from `nginx-lv3` only
     - WebRTC media (UDP 50000–60000) from Proxmox host public interface
   - Outbound: Container internet access (Tailscale egress if needed)
   - No public exposure: `browser.lv3.org` published via NGINX only to authenticated Tailscale users

**Consequences:**

**Positive:**
- Operators can debug complex browser workflows interactively without VPN/SSH friction
- Separate VM eliminates resource contention with existing message bus and artifact cache workloads
- Architectural alignment with ADR 0347 (workload isolation for I/O-sensitive services)
- Explicit timeout exception prevents silent 60s WebRTC stream failures
- Firewall locking prevents concurrent apply race conditions (addresses commit 17bc4ff5e regression)

**Negative:**
- New operational complexity: Additional VM to monitor, patch, and backup
- Network overhead: Dual paths for signalling (HTTPS) and media (UDP) require firewall ruleset expansion
- Timeout hierarchy exception: `proxy_read_timeout 3600s` is outside normal ADR 0170 bounds (requires explicit documentation and testing)
- Capacity planning: 8 vCPU + 16 GB RAM is significant; limits concurrent operator sessions to ~2–3 simultaneous browsers

**Testing & Verification:**

Three regression tests ensure past failures do not recur:

1. **Firewall Concurrency (test_neko_firewall_concurrency.py):**
   - Start Neko convergence on `runtime-comms-lv3`
   - Simultaneously apply Docker runtime workload on `docker-runtime-lv3` (sibling VM)
   - Verify Neko firewall rules persist (no clobbering via concurrent apply)
   - Passes: Firewall lock prevents rule mutation during concurrent workstream execution

2. **WebRTC Handshake (verify_neko_webrtc_session.py):**
   - Synthetic WebSocket connect to Neko signalling endpoint
   - Exchange SDP offer/answer for media negotiation
   - Verify ICE candidate flow starts (media negotiation success)
   - Timeout: 30 seconds (fails if negotiation stalls)
   - Passes: Neko responds to WebRTC protocol requirements (not just HTTP health check)

3. **Timeout Hierarchy Compliance (test_neko_timeout_hierarchy.py):**
   - Parse NGINX site config for `browser.lv3.org`
   - Assert `proxy_read_timeout 3600s` is explicitly set (not relying on defaults)
   - Verify ADR 0380 is referenced in comments or changelog (exception is documented)
   - Passes: Timeout exception is intentional, not accidental

**Related ADRs:**

- **ADR 0077:** OpenBao secret injection (Neko credentials if needed)
- **ADR 0136:** Security headers & CSP (browser access headers for WebRTC)
- **ADR 0153:** File-domain locking (firewall rule concurrency prevention)
- **ADR 0170:** Timeout hierarchy (3600s exception documented here)
- **ADR 0293:** LiveKit WebRTC deployment (reference for signalling vs media path split)
- **ADR 0347:** Docker runtime workload split (rationale for separate VM)

**Implementation Phases:**

1. **ADR approval & documentation** (this document)
2. **Ansible role creation** (`neko_runtime` role with Docker Compose template)
3. **Playbook & firewall config** (host/guest firewall rules, NGINX edge publication)
4. **Integration testing** (firewall concurrency, WebRTC handshake, timeout validation)
5. **Release management** (version bump, changelog, topology regeneration)

See implementation plan at `/Users/live/.claude/plans/async-finding-reef.md` for detailed phases, file lists, and verification checklist.
