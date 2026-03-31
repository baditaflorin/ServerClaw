# ADR 0308: LLM Agent Execution Surface and Connectivity Contracts for Operator Provisioning

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.0.0
- Implemented In Platform Version: 0.0.0
- Implemented On: 2026-03-31
- Date: 2026-03-31

## Context

When an LLM agent (Claude Code or equivalent) is asked to provision a new operator account — including
temporary guest accounts per ADR 0307 — it faces a non-obvious connectivity puzzle that cannot be
inferred from the codebase alone:

1. `scripts/operator_manager.py` exists and passes dry-run locally.
2. The Windmill onboard script (`config/windmill/scripts/operator-onboard.py`) exists and looks runnable.
3. `make operator-onboard` exists with clear arguments.

None of these work from the developer's laptop without understanding the network topology.
An agent that attempts them naively will spend significant time diagnosing mTLS errors, 502 gateway
failures, and connection-refused errors before understanding why.

This ADR records the correct execution surface, the network topology, diagnostic procedure, and
prerequisite checks so that future agents can orient immediately rather than rediscovering the
constraints ad-hoc.

## Decision

### Canonical execution surface

The `operator_manager.py onboard` command **must run from within the Docker network on VM 120
(`docker-runtime-lv3`, LAN IP `10.10.10.20`)**. The correct trigger is the Windmill workflow
`operator-onboard`, which runs on that VM and has plain HTTP access to all required services.

The correct invocation for an LLM agent is:

```
1. Ensure operators.yaml is updated with the new operator entry (can be done from the Mac).
2. Trigger the Windmill workflow via Windmill API (preferred), OR
3. SSH to the Proxmox host and run the script remotely with LV3_OPENBAO_URL overridden.
```

Do NOT attempt to run `make operator-onboard` or `uvx ... operator_manager.py onboard` from the
developer Mac directly against live services. It will fail.

### Network topology

```
Developer Mac (100.64.0.3 on Tailscale)
  │
  └─ SSH/Tailscale ──► Proxmox host (100.64.0.1, subnet router)
                            │
                            └─ LAN ──► docker-runtime VM (10.10.10.20, VM 120)
                                            │
                                            ├─ OpenBao container  (Docker internal: lv3-openbao:8201 HTTP)
                                            ├─ Keycloak container (Docker internal: lv3-keycloak:8080)
                                            ├─ Windmill container (Docker internal: lv3-windmill:8000)
                                            └─ step-ca container  (Docker internal: lv3-step-ca:9000)
```

**External exposure via Tailscale proxy** (systemd socket units on Proxmox host):

| Service   | Tailscale endpoint          | Docker-internal endpoint    | TLS | Client cert required |
|-----------|-----------------------------|-----------------------------|-----|----------------------|
| OpenBao   | `https://100.64.0.1:8200`   | `http://lv3-openbao:8201`   | yes | **yes (mTLS)**       |
| Keycloak  | `https://sso.lv3.org`       | `http://10.10.10.20:18080`  | yes | no                   |
| Windmill  | `http://100.64.0.1:8005`    | `http://10.10.10.20:8000`   | no  | no                   |
| step-ca   | via Tailscale proxy         | Docker-internal             | yes | no                   |

**Critical constraint**: OpenBao's only externally accessible port (`8200`) requires mutual TLS
(`tls_require_and_verify_client_cert = true`). `operator_manager.py` uses plain `urllib.request`
with no client-cert support. Running it from the Mac against the external endpoint fails with
`TLSV13_ALERT_CERTIFICATE_REQUIRED`. There is no workaround that does not involve modifying the
platform code or issuing a client cert via step-ca.

### SSH access from the Mac

The private key for the `ops` user on the Proxmox host lives at:

```
.local/ssh/hetzner_llm_agents_ed25519
```

The corresponding public key is authorized on the Proxmox host (`ops@100.64.0.1`).
The same key authorizes access through the ops user. Use:

```bash
ssh -i .local/ssh/hetzner_llm_agents_ed25519 \
    -o StrictHostKeyChecking=no \
    ops@100.64.0.1 '<command>'
```

The Proxmox host **cannot** reach the docker-runtime VM (`10.10.10.20`) via SSH from the `ops` user
account — the ops SSH key is not authorized on `10.10.10.20`. Docker-internal service access from
the Proxmox host is via `nc` / TCP port probing only.

### Service health check procedure

Before attempting any provisioning, an agent should verify all three backend services are up:

```bash
# 1. Check Keycloak (public URL)
curl -s -o /dev/null -w "%{http_code}" https://sso.lv3.org/realms/lv3
# Expected: 200. If 502: Keycloak container is down on docker-runtime VM.

# 2. Check OpenBao (mTLS endpoint — just verify TCP + TLS handshake, not API)
openssl s_client -connect 100.64.0.1:8200 -CAfile .local/step-ca/certs/root_ca.crt < /dev/null 2>/dev/null | grep -E "Verify|CONNECTED"
# Expected: "Verify return code: 0 (ok)". If EOF/timeout: OpenBao socket not active.

# 3. Check Windmill (via Proxmox host since Tailscale proxy may be down)
ssh -i .local/ssh/hetzner_llm_agents_ed25519 ops@100.64.0.1 \
    'nc -z -w3 10.10.10.20 8000 && echo "up" || echo "down"'
# Expected: "up". If "Connection refused": Windmill container is down.
```

If any service is down, operator provisioning cannot complete. Do not proceed — record the failure
and ask the user to check service health on VM 120.

### Windmill API trigger (preferred path)

When Windmill is up, trigger the workflow via its API. The superadmin token is stored at:

```
.local/windmill/superadmin-token.txt   (if populated by Ansible)
```

Or retrieve it from OpenBao (requires OpenBao to be sealed/unsealed first).

```bash
WM_TOKEN=$(cat .local/windmill/superadmin-token.txt)
WM_URL="http://100.64.0.1:8005"    # or tunnel: ssh -L 18000:10.10.10.20:8000 ops@100.64.0.1

curl -s -X POST "$WM_URL/api/w/lv3/jobs/run/f/platform/operator-onboard" \
  -H "Authorization: Bearer $WM_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Florin Badita",
    "email": "florin@badita.org",
    "role": "admin",
    "operator_id": "florin-tmp-001",
    "keycloak_username": "florin.badita-tmp",
    "tailscale_login_email": "florin@badita.org",
    "bootstrap_password": "'$(cat .local/keycloak/bootstrap-admin-password.txt)'"
  }'
```

### Remote script execution path (fallback)

If Windmill is unavailable but the docker-runtime VM is accessible via SSH from the Proxmox host:

```bash
# Not currently possible — ops SSH key not authorized on 10.10.10.20.
# Future: add ops public key to docker-runtime VM's authorized_keys.
# Once authorized:
ssh -i .local/ssh/hetzner_llm_agents_ed25519 ops@100.64.0.1 \
  "ssh ops@10.10.10.20 'cd /srv/proxmox_florin_server && \
   LV3_OPENBAO_URL=http://lv3-openbao:8201 \
   uvx --with pyyaml python scripts/operator_manager.py onboard \
     --name \"Florin Badita\" \
     --email \"florin@badita.org\" \
     --role admin \
     --id florin-tmp-001'"
```

### operators.yaml editing (always works from Mac)

Editing `config/operators.yaml` to pre-populate the operator record can always be done from the Mac
via the repo worktree. The dry-run also works from the Mac:

```bash
cd /path/to/repo && uvx --with pyyaml python scripts/operator_manager.py onboard \
  --name "NAME" --email "EMAIL" --role admin --id ID \
  --keycloak-username USERNAME \
  --ssh-key "$(cat /path/to/key.pub)" \
  --dry-run
```

Dry-run validates the operator record shape, generates the correct YAML, and shows what the
live run would do — without contacting any services.

### Generating a temporary SSH keypair

Admin-role operators require an SSH public key. If the collaborator has not yet provided one, generate
a temporary pair:

```bash
ssh-keygen -t ed25519 -C "<id>@lv3 (expires <date>)" -f /tmp/<id> -N ""
# Public key: /tmp/<id>.pub  → goes into operators.yaml ssh.public_keys
# Private key: /tmp/<id>     → hand to the collaborator securely; delete after delivery
```

## Consequences

**Positive**
- Future agents have a single reference for where to run provisioning commands and why
- The health check procedure fails fast instead of spending tokens on dead ends
- The network topology is documented in one place rather than scattered across Ansible vars and service catalog
- The SSH key location is explicit — no hunt across `.local/` subdirectories

**Negative / Trade-offs**
- The "correct path" (Windmill API trigger) requires Windmill to be up; there is no fully local fallback today
- The remote script fallback requires the ops SSH key to be authorized on the docker-runtime VM (not yet the case)
- `operator_manager.py` has no client-cert support, making the mTLS endpoint permanently inaccessible from the Mac without code changes

## Gap Register

These gaps make the workflow more fragile than it should be. Each is tracked here for prioritization:

| Gap | Impact | Fix |
|-----|--------|-----|
| `operator_manager.py` has no SSL client-cert support | Can only call OpenBao from Docker-internal network | Add `LV3_OPENBAO_CLIENT_CERT` / `LV3_OPENBAO_CLIENT_KEY` env var support to `platform/operator_access/http.py` |
| ops SSH key not authorized on `docker-runtime-lv3` | No fallback path when Windmill is down | Add `hetzner_llm_agents_ed25519.pub` to ops authorized_keys on VM 120 |
| No `.local/windmill/superadmin-token.txt` convention | Windmill API trigger requires manual token lookup | Ansible role for Windmill should persist the superadmin token to `.local/windmill/` |
| Service health not checked before provisioning attempt | Agents waste turns on connection errors | Add preflight health check to `scripts/preflight_controller_local.py` for operator-onboard |

## Related ADRs

- ADR 0043: OpenBao (why mTLS is required; cert issuance via step-ca)
- ADR 0044: Windmill (the canonical execution surface for this workflow)
- ADR 0056: Keycloak SSO (user provisioning target)
- ADR 0108: Operator onboarding workflow (the procedure this ADR annotates with connectivity contracts)
- ADR 0307: Temporary guest operator accounts (the use case that triggered this ADR)
