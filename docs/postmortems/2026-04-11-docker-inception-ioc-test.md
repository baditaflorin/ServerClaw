# Postmortem: Docker Inception Test — End-to-End IoC Validation

| Field | Value |
|---|---|
| **Date** | 2026-04-11 |
| **Scope** | Docker dev environment + ADR 0409 IoC override validation |
| **Profiles tested** | Minimal (3 containers), Full (7 containers) |
| **Outcome** | SSH + Ansible ping working; convergence blocked by host pattern mismatch |

## Objective

Test the generic-by-default codebase (ADR 0409) end-to-end using Docker dev.
Validate that:
1. Containers start and are reachable from the host
2. `.local/identity.yml` correctly overrides generic values at runtime
3. Ansible convergence works against Docker containers
4. Both Minimal (3-container) and Full (7-container) profiles work

## Test Results Summary

| Test | Minimal (3) | Full (7) | Notes |
|------|-------------|----------|-------|
| Container startup | PASS (30s) | PASS (31s) | Cached image; clean build ~130s |
| SSH connectivity | PASS 3/3 | PASS 7/7 | Via localhost port mappings |
| Ansible ping | PASS 3/3 | PASS 7/7 | `inventory_dir` path fix needed |
| Ansible fact gathering | PASS | PASS | Debian 12 Bookworm confirmed |
| IoC variable override | PASS | PASS | All 6 key values overridden |
| Ansible convergence | BLOCKED | BLOCKED | Playbook host patterns don't match Docker inventory names |
| Resource usage (idle) | ~15 MB | ~35 MB | ~5 MB per container (SSH only — no services deployed) |

## Findings (in discovery order)

### Finding 1: `/run/sshd` Missing — tmpfs Wipes Build-Time Directories

**Severity**: Critical — blocks all containers from starting

The Dockerfile creates `/run/sshd` during build, but `docker-compose.yml`
mounts tmpfs at `/run`, erasing the directory. SSH fails:
```
Missing privilege separation directory: /run/sshd
```

**Fix**: Added `mkdir -p /run/sshd` to `entrypoint.sh` (runs after tmpfs mount).

### Finding 2: Port 8080 Conflict

**Severity**: Medium — blocks startup on developer machines with busy ports

Default `8080:80` and `8443:443` port mappings conflict with other containers.

**Fix**: Made ports configurable via `EDGE_HTTP_PORT` / `EDGE_HTTPS_PORT`
environment variables. Default HTTP changed to 9080 to avoid common conflicts.

### Finding 3: Tailscale/VPN Subnet Collision (10.10.10.0/24)

**Severity**: Critical — silently routes traffic to production VMs

Docker dev used 10.10.10.0/24 — same as production. When Tailscale is active:
- `ssh ops@10.10.10.10` → reaches **real nginx-lv3 production VM**
- `ssh ops@10.10.10.50` → times out (production firewall blocks)
- SSH "successes" to Docker containers were false positives

**Fix**: Changed subnet to 10.99.10.0/24. The entire 172.16.0.0/12 range was
consumed by other Docker networks on this machine (/16 allocations).

**Lesson**: Docker Desktop's default IPAM aggressively consumes /16 blocks.
The 172.x range is unreliable for custom subnets on machines with many Docker
projects. The 10.x range (outside Tailscale routes) is safer.

### Finding 4: macOS Docker Desktop Cannot Route to Container Bridge IPs

**Severity**: Critical — Ansible cannot reach containers by bridge IP

On macOS Docker Desktop, container IPs on custom bridge networks are
**unreachable from the host**. Unlike Linux (where bridge IPs are routable),
macOS runs Docker in a hidden Linux VM:

```
$ ping -c 1 10.99.10.10
100.0% packet loss
```

This means the entire Docker dev design (which assumed direct IP access)
is non-functional on macOS.

**Fix**: Added SSH port mappings to all containers:
```yaml
ports:
  - "2210:22"   # nginx-edge
  - "2220:22"   # docker-runtime
  - "2230:22"   # docker-build
  - "2240:22"   # monitoring-vm
  - "2250:22"   # postgres-vm
  - "2260:22"   # backup-vm
  - "2292:22"   # runtime-control
```

Port scheme: `22xx` where `xx` = last octet of container IP.

Updated `hosts-docker.yml` to use `ansible_host: 127.0.0.1` with
`ansible_port: 22xx` instead of direct bridge IPs.

### Finding 5: SSH Key Path Resolution — `playbook_dir` vs `inventory_dir`

**Severity**: Medium — Ansible ping fails until fixed

The inventory used `playbook_dir ~ '/../.local'` for the SSH key path.
When running `ansible` (not `ansible-playbook`), `playbook_dir` resolves
to the current working directory's parent, producing an invalid path.

**Fix**: Changed to `inventory_dir ~ '/../.local'` which always resolves
relative to the inventory file's location.

### Finding 6: Ubuntu Base Image — Playbooks Require Debian

**Severity**: Critical — all convergence fails immediately

The Dockerfile used `ubuntu:24.04` but playbooks assert
`ansible_distribution == "Debian"`. Production VMs run Debian Bookworm.

```
fatal: [nginx-docker]: FAILED! => {
    "assertion": "ansible_distribution == \"Debian\"",
    "msg": "This playbook only supports Debian targets."
}
```

**Fix**: Changed base image to `debian:bookworm-slim`. Also updated Docker
CLI apt repository from `download.docker.com/linux/ubuntu` to
`download.docker.com/linux/debian`.

### Finding 7: Playbook Host Patterns Don't Match Docker Inventory

**Severity**: Critical — convergence cannot proceed

Playbooks like `public-edge.yml` target `hosts: nginx` but the Docker
inventory names the host `nginx-docker`. The `playbook_execution_host_patterns`
system exists but playbooks don't consistently use it:

```yaml
# public-edge.yml — uses direct host name
hosts: "{{ 'nginx-staging' if env == 'staging' else 'nginx' }}"

# Docker inventory has:
nginx-docker:
  ansible_host: 127.0.0.1
  ansible_port: 2210
```

This means **convergence cannot proceed** until either:
1. Playbooks are updated to use the pattern system for all host references
2. The Docker inventory adds aliases matching production host names
3. A host_vars shim maps `nginx` to `nginx-docker` in docker-dev mode

**Status**: Open — requires architectural decision

### Finding 8: IoC Identity Override — Fully Functional

**Severity**: Positive

The Ansible extra-vars override mechanism works exactly as designed:

| Variable | Committed | Local Override | Result |
|----------|-----------|---------------|--------|
| `platform_domain` | `example.com` | `lv3.org` | Override wins |
| `platform_operator_email` | `operator@example.com` | real email | Override wins |
| `platform_operator_name` | `Platform Operator` | real name | Override wins |
| `management_ipv4` | not in committed | real IP | Injected |
| `management_gateway4` | not in committed | real gateway | Injected |
| `management_ipv6` | not in committed | real IPv6 | Injected |

The injection mechanism in `platform/ansible/execution_scopes.py`:
```python
def _resolve_identity_override(repo_root: Path) -> list[str]:
    local_identity = repo_root / ".local" / "identity.yml"
    if local_identity.is_file():
        return ["-e", f"@{local_identity}"]
    return []
```

### Finding 9: Certificate Validator Blocks Push on Generic Domains

**Severity**: Medium — blocks git push

The pre-push hook validates TLS certificates for committed domains.
After ADR 0409, this means validating `proxmox.example.com` which has
no real certificate, producing `cert_mismatch` and blocking push.

**Workaround**: `SKIP_REMOTE_GATE=1` with bypass waiver.
**Fix needed**: Skip validation when domain is `example.com`.

## Timing Data

| Operation | Minimal (3) | Full (7) |
|-----------|-------------|----------|
| Clean build + start | 130s | ~135s |
| Cached start | 30s | 31s |
| SSH verify (all hosts) | 3s | 7s |
| Ansible ping (all hosts) | 2s | 3s |
| Ansible check mode (site.yml) | 8s | — |
| RAM usage (idle, SSH only) | 15 MB | 35 MB |
| Per-container RAM (idle) | 5 MB | 5 MB |

**Important**: These RAM figures reflect idle containers running only the SSH
daemon. No platform services (PostgreSQL, Keycloak, Nginx, etc.) were deployed
because convergence is blocked by host pattern mismatch (Finding 7). Actual
service RAM will be significantly higher — see ADR 0410 estimates:
micro 2 GB, minimal 4 GB, standard 16 GB, extended 32 GB. These projections
remain valid and should not be compared to the idle measurements above.

## User Journey Gaps

What an operator actually experiences trying Docker dev today:

### Step 1: `make docker-dev-up`
- **Undocumented**: Must have `.local/ssh/bootstrap.id_ed25519.pub` (run `make init-local` first)
- **Undocumented**: Port 8080 may be in use; no error guidance
- **Missing**: No `--help` or preflight check output

### Step 2: `make docker-dev-verify`
- **Broken on macOS**: Verifies using bridge IPs which are unreachable
- **Missing**: Should tell user which ports to use for SSH

### Step 3: `make docker-dev-converge`
- **Broken**: Uses `site.yml` which hits host pattern mismatch immediately
- **Missing**: No guidance on which individual playbooks to try
- **Missing**: No `--check` (dry-run) mode in the Makefile target
- **Missing**: No `.local/identity.yml` injection in the converge target

### Step 4: Debugging failures
- **Missing**: No `make docker-dev-logs` target
- **Missing**: No `make docker-dev-ssh <container>` helper
- **Missing**: No `make docker-dev-status` showing all container states

### Recommended Makefile Additions

```makefile
docker-dev-status:     ## Show container status and port mappings
docker-dev-logs:       ## Show logs from all containers
docker-dev-ssh:        ## SSH to a specific container (usage: make docker-dev-ssh VM=postgres)
docker-dev-converge-check: ## Dry-run convergence (check mode)
```

## Action Items

| # | Priority | Item | Status |
|---|----------|------|--------|
| 1 | P0 | Fix `/run/sshd` in entrypoint | Done |
| 2 | P0 | Make edge ports configurable | Done |
| 3 | P0 | Change subnet to 10.99.10.0/24 | Done |
| 4 | P0 | Add SSH port mappings for macOS | Done |
| 5 | P0 | Fix SSH key path (`inventory_dir`) | Done |
| 6 | P0 | Switch base image to Debian | Done |
| 7 | P0 | Update full compose with SSH ports | Done |
| 8 | P1 | Fix playbook host pattern mismatch | Open |
| 9 | P1 | Fix cert validator for generic domains | Open |
| 10 | P1 | Add helper Makefile targets (logs, ssh, status) | Open |
| 11 | P2 | Test actual service convergence (post host fix) | Open |
| 12 | P2 | Document Docker dev user journey end-to-end | Open |

## Key Learnings

1. **Never trust "works" without ping -c1**: The earlier SSH test showed "OK"
   because the sandbox masked timeouts. Only `ansible -m ping` gives a
   reliable connectivity signal.

2. **macOS Docker Desktop is fundamentally different from Linux Docker**:
   Bridge network IPs are unreachable from the host. Any Docker dev
   environment that assumes direct bridge IP access is Linux-only.
   Port mappings are the only reliable cross-platform approach.

3. **Test with the distribution you deploy**: Using Ubuntu in dev when
   production runs Debian catches zero real issues and adds false failures.

4. **Docker's IPAM consumes /16 blocks**: On a machine with many Docker
   projects, the entire 172.16.0.0/12 private range can be consumed.
   Use the 10.0.0.0/8 range (avoiding Tailscale subnets) instead.

5. **Host pattern indirection is incomplete**: The `playbook_execution_host_patterns`
   system handles some playbooks but not all. Playbooks that use direct
   `hosts:` references bypass it entirely. This creates a gap between
   "Ansible can reach the host" and "Ansible can run plays against it."

6. **The IoC pattern works perfectly**: The identity override via `-e @.local/identity.yml`
   is correctly implemented and all values override as expected. The
   infrastructure layer (Docker) has the bugs, not the IoC architecture.

7. **Idle RAM is not service RAM**: The vm-base image (Debian + SSH) uses
   ~5 MB per container idle, but this is meaningless for capacity planning.
   No platform services were deployed (convergence blocked by Finding 7).
   The ADR 0410 RAM estimates (4 GB minimal, 16 GB standard, 32 GB extended)
   are projections for converged services and remain valid. Real service
   RAM can only be measured after the host pattern mismatch is resolved
   and actual convergence completes.
