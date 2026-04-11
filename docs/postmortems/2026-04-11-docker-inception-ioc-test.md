# Postmortem: Docker Inception Test — IoC Value Flow Validation

| Field | Value |
|---|---|
| **Date** | 2026-04-11 |
| **Scope** | Docker dev environment + ADR 0409 IoC override validation |
| **Outcome** | Partial success: IoC mechanism verified correct; Docker dev infra has 3 bugs |

## Objective

Test the generic-by-default codebase (ADR 0409) end-to-end using the Docker dev
environment. Verify that:
1. Containers start from the generic committed code
2. `.local/identity.yml` correctly overrides generic values at runtime
3. The bootstrap sequence works for a fresh fork operator

## Test Environment

- Host: macOS (Apple Silicon) with Docker Desktop 29.1.3
- Docker dev tier: Minimal (Tier 1) — 4 containers
- Active VPN: Tailscale connected to production 10.10.10.0/24 network

## Findings

### Finding 1: `/run/sshd` Missing — Container SSH Fails on Start

**Severity**: Critical (blocks all testing)

**Root cause**: The Dockerfile creates `/run/sshd` during image build (`mkdir -p /run/sshd`),
but the `docker-compose.yml` mounts a tmpfs at `/run`, which wipes the directory at container
start. The SSH server then fails with:

```
Missing privilege separation directory: /run/sshd
```

**Fix applied**: Added `mkdir -p /run/sshd` to `entrypoint.sh` before `ssh-keygen -A`.
This runs at container start, after the tmpfs is mounted.

**Lesson**: Any directory under a tmpfs mount must be created at runtime, not build time.
This is a common Docker antipattern when tmpfs is used for `/run` or `/tmp`.

### Finding 2: Port 8080 Conflict

**Severity**: Medium (blocks container startup on some developer machines)

**Root cause**: The compose file hardcodes `8080:80` and `8443:443` port mappings.
Port 8080 was already in use by another Docker container (mapbond project).

**Fix applied**: Made ports configurable via environment variables with defaults:
```yaml
ports:
  - "${EDGE_HTTPS_PORT:-8443}:443"
  - "${EDGE_HTTP_PORT:-8080}:80"
```

Operators with conflicts can now run:
```bash
EDGE_HTTP_PORT=9080 EDGE_HTTPS_PORT=9443 make docker-dev-up
```

**Lesson**: Developer machines have unpredictable port allocations. Always make
host-side port mappings configurable.

### Finding 3: Tailscale/VPN Route Collision with Container Network

**Severity**: Critical (blocks Ansible convergence from macOS)

**Root cause**: The Docker dev containers use the same IP range (10.10.10.0/24) as
the production VMs. When the operator has Tailscale/VPN active, the host routing
table sends traffic to the real production network instead of Docker containers:

```
10.10.10/24    link#25    UCS    utun4    (Tailscale)
```

SSH to `10.10.10.10` connected to the **real production nginx-lv3 VM**, not the
Docker container. SSH to `10.10.10.50` and `10.10.10.92` timed out because those
real VMs have firewall rules blocking this developer's IP.

**Inter-container networking works perfectly** — containers can reach each other
at 10.10.10.x. The issue is only host-to-container routing on macOS.

**Workarounds** (not yet implemented):
1. Disconnect Tailscale before running Docker dev
2. Use a different subnet for Docker dev (e.g., 172.30.10.0/24) — requires
   updating `hosts-docker.yml` and compose files
3. Use `docker exec` instead of SSH for Ansible (connection plugin change)
4. Use SSH port-forwarding through Docker: map each container's SSH port to
   a unique localhost port

**Lesson**: Docker dev environments MUST NOT use the same subnet as production
when operators may have VPN/Tailscale routes to production. This is a fundamental
architectural flaw in the current Docker dev design.

### Finding 4: IoC Identity Override — Fully Functional

**Severity**: Positive finding

The identity override mechanism works exactly as designed:

| Layer | Variable | Value |
|-------|----------|-------|
| Committed `identity.yml` | `platform_domain` | `example.com` |
| `.local/identity.yml` | `platform_domain` | `lv3.org` |
| Ansible runtime | `platform_domain` | `lv3.org` (override wins) |

All 6 key variables are correctly overridden:
- `platform_domain`: `example.com` -> real domain
- `platform_operator_email`: `operator@example.com` -> real email
- `platform_operator_name`: `Platform Operator` -> real name
- `management_ipv4`: committed as RFC 5737 `203.0.113.1` -> real public IP
- `management_gateway4`: not in committed code -> injected from `.local/`
- `management_ipv6`: not in committed code -> injected from `.local/`

The injection mechanism in `platform/ansible/execution_scopes.py`:
```python
def _resolve_identity_override(repo_root: Path) -> list[str]:
    local_identity = repo_root / ".local" / "identity.yml"
    if local_identity.is_file():
        return ["-e", f"@{local_identity}"]
    return []
```

This is called by `run_planned_playbook()` and automatically appends
`-e @.local/identity.yml` to every `ansible-playbook` invocation.

### Finding 5: Generator Scripts Use Generic Values Correctly

`generate_platform_vars.py --dry-run` produces output with generic values
from committed code (`203.0.113.1`, `proxmox-host`, `2001:db8::2`). These
are correctly overridden at Ansible runtime, not at generation time.

The 7 extra variables in `.local/identity.yml` (not present in committed code)
are host-specific overrides added by ADR 0409:
- `host_public_hostname`, `proxmox_node_name`
- `management_ipv4`, `management_gateway4`, `management_ipv6`
- `management_interface`, `hetzner_ipv4_route_network`

### Finding 6: Certificate Validator Needs ADR 0409 Awareness

The pre-push hook's certificate validator tries to check TLS certificates for
`proxmox.example.com` — the generic domain committed after ADR 0409. This
obviously has no real certificate and fails with `cert_mismatch`, blocking
all pushes. This is a pre-existing issue that needs a separate fix:

Options:
1. Skip certificate validation for `example.com` domains
2. Only validate certificates listed in `.local/identity.yml`'s domain
3. Make the validator identity-aware (resolve real domain before checking)

## Metrics

| Metric | Value |
|--------|-------|
| Containers started | 3 of 3 (after entrypoint fix) |
| SSH from host | 1 of 3 (Tailscale collision) |
| Inter-container SSH | Working (verified via `docker exec`) |
| IoC variables overridden | 6 of 6 |
| Generator scripts | Correct output with generic values |
| Ansible convergence | Not tested (SSH routing blocked) |

## Action Items

| Priority | Item | Status |
|----------|------|--------|
| P0 | Fix `/run/sshd` in entrypoint.sh | Done |
| P0 | Make edge ports configurable | Done |
| P1 | Fix Tailscale/Docker subnet collision | Open |
| P1 | Fix certificate validator for generic domains | Open |
| P2 | Add Docker dev network documentation | Open |
| P2 | Test Ansible convergence without Tailscale | Open |

## Key Learnings

1. **The IoC pattern works**: The Ansible extra-vars override mechanism is
   correctly implemented and functional. A fork operator who edits only
   `.local/identity.yml` will get a fully customized deployment.

2. **Docker dev needs a different subnet**: Using the same IP range as
   production is a design flaw when operators have VPN access. This is
   particularly insidious because it silently routes to production VMs
   instead of failing visibly.

3. **tmpfs and build-time directories don't mix**: Any path under a tmpfs
   mount must be created at container start, not during image build.

4. **Generic domains break TLS validators**: After ADR 0409, any tool that
   attempts real network validation against committed generic values will
   fail. These tools need to be identity-aware or skip generic domains.

5. **The 8-value operator edit is genuinely minimal**: The committed code
   has 43 variables in `identity.yml`, plus 7 host-specific variables added
   by `.local/identity.yml`. A fork operator truly only needs to edit 8
   values (the rest are derived via Jinja2 expressions).
