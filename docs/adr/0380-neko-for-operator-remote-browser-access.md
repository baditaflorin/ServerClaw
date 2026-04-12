# ADR 0380: Neko Remote Desktop for Interactive Operator Browser Access

- Status: Accepted
- Implementation Status: Live applied
- Implemented In Repo Version: 0.178.126
- Implemented In Platform Version: 0.178.78
- Implemented On: 2026-04-12
- Date: 2026-04-06
- Tags: browser, remote-desktop, webrtc, operator-access, runtime-comms

## Context

The platform already runs **headless browser automation** through the Playwright
browser-runner on `docker-runtime`. That path is useful for scripted checks, but it
does not help when an operator needs a fully interactive browser session for tasks
such as:

- debugging third-party OAuth or SAML flows
- manually reproducing UI failures
- visually inspecting browser behavior during operational incidents
- exploring a target site without first writing automation

Previous attempts to serve real-time browser access through the platform exposed
three recurring risks:

1. **WebRTC media forwarding drift.** UDP media rules on the Proxmox host could
   be lost when unrelated convergence touched sibling services.
2. **Timeout hierarchy mismatches.** Browser signalling uses long-lived WebSocket
   connections that fail under default short proxy timeouts.
3. **Resource contention.** Running interactive media workloads beside heavy
   Docker-runtime services caused unnecessary jitter and unpredictable failures.

The original ADR draft also described an implementation that is no longer correct:
it referenced a single-container design on `10.10.10.41`, an Ubuntu guest, and a
management-network-only access path. That design was not the final live topology
and must not be treated as the current source of truth.

## Decision

We will provide interactive operator browser access through **multi-instance Neko**
running on the dedicated `runtime-comms` VM and publish it through the shared edge
with identity-based routing.

### Runtime placement

- Service host: `runtime-comms` (`vmid 121`)
- Guest address: `10.10.10.21`
- Base OS family: Debian 13
- Isolation goal: keep interactive WebRTC/browser traffic off `docker-runtime`
  and aligned with ADR 0347's workload-partitioning direction

### Access model

- Public entrypoint: `https://browser.example.com`
- TLS terminates at the shared NGINX edge
- Access is gated by the platform's oauth2-proxy and Keycloak identity flow
- NGINX routes the authenticated operator to the correct backend by matching the
  authenticated email to a generated backend map
- Unmapped identities receive HTTP 403 rather than a shared browser session

### Signalling and media

- Each Neko instance receives an isolated TCP signalling port and a non-overlapping
  UDP media range
- HTTPS/WebSocket signalling stays behind the edge proxy
- The public internet does **not** receive a Proxmox host DNAT rule for TCP `8080`
- The Proxmox host forwards UDP `50000-60000` to `runtime-comms` so WebRTC media
  can reach the browser session directly
- Edge proxy configuration keeps the explicit long-lived timeout exception required
  by ADR 0170 for WebRTC signalling

### Provisioning and lifecycle

- `playbooks/neko.yml` is the canonical live-apply entrypoint
- The playbook replays all required surfaces for the service, including:
  - Proxmox host networking and UDP forwarding
  - `runtime-comms` Neko runtime convergence
  - DNS publication for `browser.example.com`
  - NGINX edge publication for the browser route
- `neko_instances` defines the per-operator browser backends
- Managed Keycloak users are provisioned and deprovisioned from the same declared
  instance set

### Clean-worktree guarantee

The live apply must succeed from a fresh `origin/main` worktree, not only from a
checkout that already contains generated artifacts. The implementation therefore
includes branch-local bootstrap support for:

- generated platform vars required by the scoped Neko runs
- shared edge portal artifacts used by validation paths
- receipt skeletons expected by workflow validation
- clean-worktree installation of required Ansible collections

## Consequences

### Positive

- Operators can reach an interactive browser through the normal platform edge
  instead of relying on ad hoc SSH port forwards or VPN-only workflows
- The dedicated `runtime-comms` placement avoids resource contention with busy
  Docker-runtime services
- Identity-based routing keeps sessions operator-specific rather than shared
- Exact-main replay becomes reliable because the playbook now re-applies the
  Proxmox UDP forwarding contract and its clean-checkout prerequisites

### Trade-offs

- The service depends on both edge proxy configuration and Proxmox UDP forwarding,
  so regressions can happen at more than one layer
- Long-lived WebRTC signalling still requires an explicit timeout exception from
  the default proxy hierarchy
- Operating multiple isolated browser instances increases runtime and verification
  complexity compared with a single shared container

## Regression Guards

The implementation is protected by focused automation that covers the failure modes
this ADR is trying to avoid:

- `tests/test_neko_firewall_concurrency.py`
  Guards against forwarding-rule loss during concurrent convergence.
- `tests/test_neko_timeout_hierarchy.py`
  Confirms the explicit long-lived proxy timeout remains in place.
- `tests/test_neko_ingress_contract.py`
  Verifies the public edge contract stays aligned with the Neko topology.
- `tests/test_neko_verification_contract.py`
  Ensures the controller-side verification path and clean-worktree bootstrap
  remain wired correctly.
- `tests/test_docker_runtime_role.py`
  Prevents the scoped-run argument-resolution regressions that broke exact-main
  Neko convergence.

## Verification

The 2026-04-12 live apply was verified from an exact-main replay using:

- clean-cache `make converge-neko env=production`
- `python3 scripts/neko_tool.py validate`
- `python3 scripts/verify_neko_webrtc_session.py --public-url https://browser.example.com --timeout 30`

That verification proved all of the following together:

- the public browser route reached the oauth2-protected edge
- backend selection resolved to `runtime-comms`
- websocket signalling completed
- SDP and ICE negotiation completed
- UDP media forwarding existed on the Proxmox host
- stale public TCP forwarding for Neko signalling was absent

## Operational Notes

`scripts/neko_tool.py` is the day-to-day helper for instance management and
validation. It supports listing configured instances, calculating the next free
signalling or UDP range, and validating that the declared instance set has no
port collisions before convergence.

## Related ADRs

- ADR 0077: OpenBao secret injection
- ADR 0136: Security headers and CSP
- ADR 0153: File-domain locking
- ADR 0170: Timeout hierarchy
- ADR 0293: LiveKit-style signalling and direct media split
- ADR 0347: Docker runtime workload split
