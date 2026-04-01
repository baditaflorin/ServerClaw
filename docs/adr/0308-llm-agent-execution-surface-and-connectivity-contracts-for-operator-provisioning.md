# ADR 0308: LLM Agent Execution Surface and Connectivity Contracts for Operator Provisioning

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: pending main integration
- Implemented In Platform Version: 0.130.85
- Implemented On: 2026-04-02
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

The `operator_manager.py onboard` command **must run where OpenBao is reachable over plain HTTP**.
There are now two verified ways to satisfy that constraint:

1. **Preferred**: trigger the Windmill worker path `f/lv3/operator_onboard` on VM 120
   (`docker-runtime-lv3`, LAN IP `10.10.10.20`). The worker runtime sets
   `LV3_OPENBAO_URL=http://lv3-openbao:8201` and runs inside the exact network that can reach the
   required services.
2. **Fallback**: SSH to `docker-runtime-lv3` and run `scripts/operator_manager.py onboard` from the
   guest host with `LV3_OPENBAO_URL=http://127.0.0.1:8201`.

Do **not** attempt to run `make operator-onboard` or `scripts/operator_manager.py onboard` from the
developer Mac against the default service-catalog OpenBao URL. The controller-side default still
points at the private mTLS listener on `https://100.64.0.1:8200`, and `operator_manager.py` does
not speak client-certificate TLS yet.

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
The same key is also authorized on `docker-runtime-lv3`. Use:

```bash
ssh -i .local/ssh/hetzner_llm_agents_ed25519 \
    -o StrictHostKeyChecking=no \
    ops@100.64.0.1 '<command>'
```

For guest access, prefer the explicit proxy form because the `-J` shorthand does not always carry
the correct identity arguments from an arbitrary workstation shell:

```bash
ssh -i .local/ssh/hetzner_llm_agents_ed25519 \
    -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o ProxyCommand='ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' \
    ops@10.10.10.20 '<command>'
```

That path was re-verified on 2026-04-02 from the controller worktree.

### Service health check procedure

Before attempting any provisioning, run the repo-managed preflight:

```bash
make preflight WORKFLOW=operator-onboard
```

As of 2026-04-02 that preflight checks:

```bash
# 1. Check Keycloak (public discovery contract)
curl -fsS https://sso.lv3.org/realms/lv3/.well-known/openid-configuration >/dev/null

# 2. Check OpenBao (private mTLS listener)
openssl s_client -connect 100.64.0.1:8200 -CAfile .local/step-ca/certs/root_ca.crt < /dev/null 2>/dev/null | grep -q "Verify return code: 0 (ok)"

# 3. Check Windmill (private host proxy contract)
curl -fsS http://100.64.0.1:8005/api/version >/dev/null
```

If any service is down, operator provisioning cannot complete. Do not proceed — record the failure
and repair the dependency first. The 2026-04-02 implementation now fails closed through
`scripts/preflight_controller_local.py` instead of relying on manual memory alone.

### Windmill API trigger (preferred path)

When Windmill is up, prefer the helper that resolves the current script metadata and submits through
the supported `run_wait_result` path. The managed bootstrap secret lives at:

```
.local/windmill/superadmin-secret.txt
```

```bash
WINDMILL_TOKEN="$(tr -d '\n' < .local/windmill/superadmin-secret.txt)" \
python3 scripts/windmill_run_wait_result.py \
  --base-url http://100.64.0.1:8005 \
  --workspace lv3 \
  --path f/lv3/operator_onboard \
  --payload-json '{
    "name": "Florin Badita",
    "email": "florin@badita.org",
    "role": "admin",
    "operator_id": "florin-tmp-001",
    "keycloak_username": "florin.badita-tmp",
    "tailscale_login_email": "florin@badita.org",
    "bootstrap_password": "'"$(cat .local/keycloak/bootstrap-admin-password.txt)"'"
  }'
```

For a no-mutation smoke, pass `"dry_run": true` and a `viewer` role payload.

### Remote script execution path (fallback)

If Windmill is unavailable, the guest-host fallback is now available directly from the Mac through
the same `ops` key:

```bash
ssh -i .local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand='ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' \
  ops@10.10.10.20 \
  'cd /srv/proxmox_florin_server && \
   LV3_OPENBAO_URL=http://127.0.0.1:8201 \
   uv run --with pyyaml python scripts/operator_manager.py onboard \
     --name "Florin Badita" \
     --email "florin@badita.org" \
     --role admin \
     --id florin-tmp-001 \
     --ssh-key "@/tmp/florin.pub" \
     --emit-json'
```

For a controller-local live read path without switching execution surfaces, forward OpenBao to a
loopback automation port first:

```bash
ssh -f -N \
  -i .local/ssh/hetzner_llm_agents_ed25519 \
  -o IdentitiesOnly=yes \
  -o ExitOnForwardFailure=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand='ssh -i .local/ssh/hetzner_llm_agents_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ops@100.64.0.1 -W %h:%p' \
  -L 18201:127.0.0.1:8201 \
  ops@10.10.10.20

LV3_OPENBAO_URL=http://127.0.0.1:18201 \
uv run --with pyyaml python scripts/operator_access_inventory.py --id florin-badita
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
- The preferred Windmill path still requires Windmill to be healthy on `docker-runtime-lv3`
- Controller-local live runs still require an OpenBao loopback override or tunnel because the default service catalog points at the mTLS edge
- `operator_manager.py` has no client-cert support, making the mTLS endpoint permanently inaccessible from the Mac without code changes

## Gap Register

These gaps make the workflow more fragile than it should be. Each is tracked here for prioritization:

| Gap | Impact | Fix |
|-----|--------|-----|
| `operator_manager.py` has no SSL client-cert support | Can only call OpenBao from Docker-internal network | Add `LV3_OPENBAO_CLIENT_CERT` / `LV3_OPENBAO_CLIENT_KEY` env var support to `platform/operator_access/http.py` |
| Controller-side `make operator-onboard` still resolves OpenBao through the service catalog by default | Controller-local live runs fail unless the operator knows to tunnel or override `LV3_OPENBAO_URL` | Teach the controller path to prefer a repo-managed loopback automation endpoint when one is available |
| The supported Windmill script path and token file were easy to misremember (`f/lv3/operator_onboard` vs older guesses, `superadmin-secret.txt` vs `superadmin-token.txt`) | Agents can hit the wrong API route or secret path even when the runtime is healthy | Keep ADR 0308 and `docs/runbooks/operator-onboarding.md` aligned with the live Windmill contract and re-verify after each Windmill replay |

## Related ADRs

- ADR 0043: OpenBao (why mTLS is required; cert issuance via step-ca)
- ADR 0044: Windmill (the canonical execution surface for this workflow)
- ADR 0056: Keycloak SSO (user provisioning target)
- ADR 0108: Operator onboarding workflow (the procedure this ADR annotates with connectivity contracts)
- ADR 0307: Temporary guest operator accounts (the use case that triggered this ADR)
