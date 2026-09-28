# WS-0513: Builder metrics over the private tailnet

## Status

`live_applied` — PR #252 is merged at `b3145e06e`; the merged guest policy is
applied and Builder-to-node-exporter scraping has passed end to end. The
platform patch version is `0.178.224`. The workstream is pending the next
repository release for its `included_in_repo_version` and generated receipt
index. A release cut is currently blocked by unrelated in-progress workstreams
and expired gate-waiver entries; no release was forced.

## Decision

Permit the identified Builder metrics peer to scrape the Proxmox host's
node-exporter listener over the private tailnet only. Keep the peer allow in
the host's inventory variables and render it into the cluster firewall
template. The host listener is a Tailscale-bound systemd socket proxy to the
`docker-build` VM, so the canonical guest firewall must also allow the
Proxmox internal host address to reach that VM's TCP/9100 backend. Do not
publish port 9100 to the public edge or hand-edit generated group variables.

The repository gate must validate only services whose service-owned surfaces
changed. A platform security role such as `proxmox_security` is not a service
role and must not fan out into unrelated expired legacy completeness
suppressions. Unknown service-role families and canonical service-catalog
changes remain fail-closed; the explicit full audit remains available with
`--validate`. Standalone test-only edits do not alter runtime completeness and
must not trigger a service audit; a test changed alongside its owning service
role is still covered by the role path.

The guest firewall renderer is also being made ownership-safe for hosts running
Docker: it replaces only the `inet filter` table managed by the firewall role
instead of flushing Docker's separate nftables tables. This avoids deleting
Docker NAT/filter chains and restarting Docker during an unrelated firewall
policy converge.

The first full repository gate also exposed unrelated pre-existing hygiene
failures that prevented publishing any branch: missing role-policy inventory,
ShellCheck findings, ad hoc retry implementations, and topology scanning of
ignored generated worktrees. These were corrected narrowly and tested without
weakening the gates or extending suppression dates. Stale exclusive ownership
claims on the already-merged Proxmox security task file were released; Makefile
and shell-wrapper edits now declare additive shared contracts. The full gate
also exposed a Renovate contract checker that expected a literal registry host
even though the workflow correctly uses the configured Harbor registry
variable; the checker now validates that variable-backed reference and its
digest pin.

## Scope

- Track the private tailnet TCP/9100 exception in host topology variables.
- Validate and render the narrow exception in the cluster firewall template.
- Track the existing TCP/9101 capacity-controller exception in the host
  firewall template so future reconciles preserve it.
- Allow only the Proxmox host source to reach the `docker-build` guest's
  node-exporter TCP/9100 backend used by the Tailscale-bound proxy.
- Preserve the existing `nginx` to `runtime-control` MinIO S3
  TCP/9000 allow discovered by the read-only converge preview.
- Track the live Coolify-to-API-verifier host exception documented in ADR 0481
  so a targeted firewall converge does not remove that working relay path.
- Expose a focused Proxmox firewall-policy convergence target rather than
  replaying the full security role (ACME, TFA, SSH, and user state).
- Scope changed-service completeness checks and test remote runner path
  propagation.
- Pass an explicitly selected topology overlay into validation containers via
  a single read-only file mount, so schema checks can reproduce the selected
  deployment without exposing the rest of `.local`.

## Exclusions

- No public ingress, SSH credential, or firewall bypass.
- No VM resize or storage cleanup.

## Verification

- Focused generator, service-completeness, and platform-ops tests.
- Validation-runner tests prove the selected topology is mounted read-only and
  missing selections fail before container execution.
- `make generate-platform-vars` followed by generated-variable validation; no
  generated group-variable diff is needed for this host-local input.
- Full pre-push gate, then normal branch push and PR review.
- Workstream registry remains source-generated and its active ownership
  manifests validate before branch publication.
- The full local pre-push gate passes all 16 blocking checks after the
  standalone-test completeness-scope and stale-ownership corrections.
- Focused Linux firewall, Docker runtime, and completeness-scope tests pass
  (`40 passed`); the test-only path no longer selects `docker_runtime`, while
  the existing role-plus-test test continues to select its service.
- Verify the Builder metrics peer cannot reach TCP/9100 before the apply and
  can fetch `/metrics` after it, while the existing TCP/9101 path remains
  allowed.
- Preview and converge the guest firewall policy with `--limit proxmox-host`
  so no guest-local nftables play is replayed; verify the rendered VM130 rule
  admits only the Proxmox host source on TCP/9100.
- Use the deployment-specific inventory overlay for the verified Proxmox SSH
  endpoint and port; do not disable host-key checking for the apply.
- From Builder PCT108, use the tailscaled userspace SOCKS5 listener at
  `127.0.0.1:1055` for the actual tailnet HTTP probe. A raw guest curl does not
  traverse Tailscale on this userspace-networking configuration.

## Live evidence (2026-09-28)

- The Proxmox node reports `pve-firewall` enabled/running. Its Tailscale address
  is `100.120.234.7`; the Builder peer `100.114.37.21` responds to `tailscale
  ping`.
- PR #250's cluster rule is compiled for `100.114.37.21/32` to TCP/9100. The
  pre-existing node rules for TCP/9101 and TCP/18021 remain present.
- TCP/9100 is a systemd socket proxy (`woodpecker-0exec-build-metrics-proxy`)
  to `10.10.10.30:9100` (the `docker-build` VM, VMID 130), not a listener served
  directly by the hypervisor. Its logs and a direct backend probe both showed
  timeouts.
- The live `/etc/pve/firewall/130.fw` allowed the central Prometheus peer but
  did not allow the hypervisor (`10.10.10.1/32`) used by the proxy's backend
  connection. The source fix adds only that host-to-VM TCP/9100 rule.
- The read-only guest-policy preview found VM192's live `10.10.10.10/32` to
  TCP/9000 rule was missing from canonical `runtime-control` policy. The
  deployment topology maps that source to `nginx`; the existing MinIO S3 flow
  is now recorded to prevent an unrelated deletion during the managed
  firewall reconcile.
- Before applying PR #250, the exact cluster and node firewall inputs were
  backed up under `/root/backups/ws-0513-20260928T061123Z/`; both files were
  mode 0600 and their checksums matched the live originals.
- PR #252 (`b3145e06e`) completed both Woodpecker PR and push checks. Its merged
  table-scoped guest-firewall replay on VM130 returned Ansible `ok=37
  changed=2 unreachable=0 failed=0 skipped=8 rescued=0 ignored=0`.
- The final guest policy permits the Proxmox host source `10.10.10.1/32` to
  TCP/9100. The active PVE host rule permits Builder peer `100.114.37.21/32`
  to the tailnet-bound proxy at `100.120.234.7:9100`, which forwards to
  `10.10.10.30:9100`.
- The Builder PCT108 request through `socks5h://127.0.0.1:1055` returned HTTP
  200 and a `node_uname_info` sample with `nodename="docker-build"`. Direct
  host-backend and host-proxy probes also returned HTTP 200.
- Docker's MainPID, active-start timestamp, all 18 running container IDs, and
  Docker-owned nftables NAT/filter tables were unchanged by the merged replay;
  no Docker restart or rescue was needed.
- The earlier pre-PR global nftables flush did restart Docker and left seven
  `codex-e2e` containers stopped because they use `restart=no`; all seven were
  restored before the final replay. The merged role now replaces only its own
  `inet filter` table, preventing recurrence.

## Merge criteria

1. The generated host rule is reproducible from canonical topology and
   restricted to the intended tailnet peer and TCP/9100.
2. The generated `docker-build` guest rule permits only the Proxmox host to
   reach the proxy backend on TCP/9100.
3. The live `nginx` to `runtime-control` MinIO S3 TCP/9000 flow is
   preserved by the full guest-policy renderer.
4. Changed-service validation scopes service role edits, skips unrelated
   platform roles, and still fails closed for unknown runtime/service roles
   and global catalogs.
5. Focused checks and the full impacted push gate pass without extending
   expired legacy suppressions.
