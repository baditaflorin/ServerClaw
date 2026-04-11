# Postmortem: Full Credential Rotation After Public Release

**Date:** 2026-04-11
**Severity:** CRITICAL
**ADR:** 0405 (Emergency Credential Rotation After Public Release)
**Trigger:** Public release of codebase to `github.com/baditaflorin/ServerClaw`

---

## Incident Summary

On 2026-04-11, the platform codebase was published to a public GitHub
repository with 3,339 commits of full git history. A security audit
immediately following the release identified:

- **1 active credential** exposed in the current tree (Keycloak OIDC secret)
- **1 credential** recoverable from git history (Semaphore admin password)
- **1 API token** embedded in a local git remote URL (Gitea)
- **249 secret structure entries** publicly visible (names, paths, purposes,
  rotation workflows) in `config/controller-local-secrets.json`
- **Full infrastructure topology** exposed: internal IPs, public IP, domain
  names, service-to-host mappings across 250+ files

The response was to rotate **all 226 platform-generated credentials**
programmatically, making every value recoverable from git history useless.

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| ~T+0h | Repository pushed to `github.com/baditaflorin/ServerClaw` with full git history |
| T+0h | Commit `2cb17da4f` removes Semaphore admin password from workstream doc but misses OIDC secret |
| T+1h | Security audit initiated — 5 parallel scans launched |
| T+1.5h | Audit complete: 1 live secret, 1 historical secret, 1 local token, full topology exposure identified |
| T+2h | First postmortem written (`2026-04-11-public-release-secret-exposure.md`) documenting findings |
| T+2.5h | ADR 0405 written — decision: full programmatic rotation of all 226 platform-generated credentials |
| T+3h | `scripts/emergency_credential_rotation.py` built and tested — 204 will auto-rotate, 22 manual/derived |
| T+3h | OIDC secret removed from `ws-0362-semaphore-keycloak-oidc.md` |
| T+3h | Runbook written: `docs/runbooks/emergency-credential-rotation.md` |
| T+3.5h | This postmortem written |
| Pending | Tier 1 rotation executed (3 critical secrets) |
| Pending | Tier 2 rotation executed (28 infrastructure secrets) |
| Pending | Tier 3 rotation executed (173 service secrets) |
| Pending | Full platform reconvergence completed |
| Pending | Verification: all OIDC logins, database connections, API tokens working |

---

## What Was Exposed

### Directly Exposed Credentials (3)

| Secret | Type | How Exposed | Exploitability |
|--------|------|-------------|----------------|
| Keycloak Semaphore OIDC client secret | Client Secret | Plaintext in committed file on public repo | HIGH — usable immediately for OIDC auth |
| Semaphore admin password | Password | In git history (deleted file) | MEDIUM — requires git history recovery |
| Gitea API token | Access Token | In local `.git/config` remote URL | LOW — not in git tree |

### Structural Exposure

| Category | Count | Risk |
|----------|-------|------|
| Secret names and `.local/` paths | 249 | Reveals what secrets exist and where |
| OpenBao mount paths and policies | 8 | Reveals vault structure |
| Keycloak client IDs and purposes | 14 | Enables targeted OIDC attacks |
| Rotation workflow references | 12 | Reveals automation surface |
| Internal IPs (10.10.10.x) | 20+ | Full network topology |
| Public IP (203.0.113.1) | 1 | Direct targeting |
| Domain + subdomains (example.com) | 30+ | DNS enumeration confirmed |
| Operator identity | 1 | Social engineering vector |

### What Was NOT Exposed

| Category | Status |
|----------|--------|
| SSH private keys | Never committed (`.local/ssh/` gitignored) |
| Actual secret values (except 3 above) | Stored in `.local/` — never committed |
| `.env` files | Gitignored |
| OpenBao unseal keys | In `.local/openbao/init.json` — never committed |
| Database data | Not in repository |
| Ansible Vault encrypted content | None exists in this repo |

---

## Response: Programmatic Rotation

### Tool Built

`scripts/emergency_credential_rotation.py` — a standalone rotation script that:

1. Reads `config/controller-local-secrets.json` to enumerate all 226
   `generated_by_repo` secrets
2. Classifies each into Tier 1 (critical), Tier 2 (infrastructure), or
   Tier 3 (services)
3. Selects the appropriate generator per secret type:
   - **Safe alphabet** (ADR 0403): for passwords and general secrets
   - **Hex 32/16**: for encryption keys, tokens, salts
   - **ssh-keygen**: for SSH key pairs
   - **openssl genrsa**: for RSA keys
   - **JSON password update**: for auth files with password fields
4. Writes new values to `.local/` paths with 0600 permissions
5. Produces a timestamped receipt in `receipts/credential-rotations/`
6. Prints convergence instructions for propagating new credentials

### Rotation Coverage

```
Total secrets:   226
Will auto-rotate: 204
Skipped:          22 (manual/derived — see below)
```

### Skipped Secrets (22) — Require Manual Handling

| Secret | Reason |
|--------|--------|
| `openbao_init_payload` | Contains unseal keys — only re-init if compromise confirmed |
| `nomad_tls_ca_key`, `nomad_tls_client_key`, `nomad_tls_server_key` | TLS CA chain — requires coordinated regeneration |
| `gitea_release_bundle_cosign_private_key` | Cosign keypair — requires `cosign generate-key-pair` |
| `matrix_synapse_signing_key` | Federation identity key — regeneration breaks federation |
| `backup_vm_api_token_payload`, `proxmox_api_token_payload` | Proxmox API tokens — regenerated by convergence roles |
| `proxmox_ops_pam_totp_state` | TOTP state — regenerated by TFA setup |
| `coolify_server_ssh_public_key` | Derived from private key |
| `vaultwarden_admin_token_hash` | Derived from admin token |
| `glitchtip_*_dsn` (3) | GlitchTip project DSNs — regenerated by convergence |
| `serverclaw_provider_env` | Complex env file — manual edit required |
| `control_plane_recovery_controller_bundle` | Archive — regenerated by role |
| Various JSON payloads (5) | Complex structures regenerated by convergence roles |

### Convergence Order

The runbook prescribes a specific convergence order to avoid service outages:

1. **PostgreSQL VM first** — propagates new database role passwords
2. **Keycloak** — propagates new OIDC client secrets
3. **OpenBao** — re-seeds rotated AppRole credentials
4. **Step-CA** — rotated provisioner passwords
5. **Each service alphabetically** — picks up new credentials from `.local/`

---

## Root Cause Analysis

### Why did this happen?

1. **Documentation contained a real secret** — A workstream doc
   (`ws-0362-semaphore-keycloak-oidc.md`) contained a real Keycloak client
   secret pasted inline during the OIDC integration. This is a documentation
   anti-pattern: setup guides should reference `.local/` paths, not paste
   actual values.

2. **Scrub was manual and incomplete** — The publish preparation commit
   (`31d24a6cd`) manually edited ~25 files but missed the OIDC secret in a
   workstream doc. With 250+ files referencing `example.com`, manual scrubbing
   was insufficient.

3. **Full git history was pushed** — Even files that were scrubbed in the
   final commit retained their original values in prior commits. The publish
   process should have used a squashed orphan branch or `git filter-repo`.

4. **No pre-publish secret scan** — Although gitleaks was configured in
   `.gitleaks.toml` and pre-commit hooks, no explicit "scan everything before
   push to public" gate existed.

### Why was the response effective?

1. **Comprehensive secret inventory already existed** — The
   `controller-local-secrets.json` manifest with 249 entries and
   `secret-catalog.json` with rotation metadata made it possible to
   enumerate every credential programmatically.

2. **Secrets were already externalized** — Because actual values live in
   `.local/` (never committed) and the repo only contains structure, the
   rotation was straightforward: regenerate the `.local/` files, reconverge.

3. **Ansible convergence is idempotent** — Running `make converge-<service>`
   propagates whatever value is in `.local/` to the live infrastructure.
   No manual per-service patching was needed.

4. **ADR 0403 safe alphabet** — Having a defined safe password alphabet
   meant the rotation script could generate passwords that work in all
   consumption contexts (PostgreSQL URLs, Docker env files, YAML, Jinja2)
   without encoding issues.

---

## Lessons Learned

### 1. Never paste real secrets in documentation

**Before:** Workstream docs sometimes contained real secret values for
convenience during implementation.

**After:** All documentation must reference `.local/` file paths. A gitleaks
rule will be added to catch inline Keycloak client secret patterns
(`[A-Za-z0-9+/]{40,}=`) in Markdown files.

### 2. Public releases need a squashed or filtered history

**Before:** The publish process pushed the full commit history to GitHub.

**After:** Public releases should use one of:
- `git checkout --orphan clean-release` with a single squashed commit
- `git filter-repo` to strip sensitive patterns from all history
- A separate public-only branch maintained independently

### 3. Pre-publish gates must be automated

**Before:** The publish preparation was a manual checklist applied to ~25 files.

**After:** Add a `scripts/pre_publish_audit.py` that runs before any push to
a public remote, scanning for:
- Real domain names (configurable per deployment)
- Keycloak client secret patterns
- API tokens and password literals
- Internal IP addresses in non-inventory files

### 4. Secret structure exposure is a real threat vector

**Before:** The assumption was "if values aren't committed, the structure
doesn't matter."

**After:** Knowing that `keycloak_grafana_client_secret` exists at
`.local/keycloak/grafana-client-secret.txt` and is consumed by Grafana's
OIDC configuration means an attacker who gets any lateral access knows
exactly which files to target. For future public releases, consider whether
the secret catalog should be excluded from the public repo.

### 5. A comprehensive secret inventory enables rapid incident response

**Before (hypothetical):** Without `controller-local-secrets.json`, rotating
all credentials would require manually tracing every role's secrets.

**After:** The manifest made it possible to build a rotation script in under
an hour that covers 204 of 226 secrets automatically. The investment in
cataloging secrets (ADR 0065, ADR 0141) paid off immediately during this
incident.

---

## Action Items

| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | Execute T1 rotation (3 critical secrets) | Operator | Pending |
| 2 | Execute T2 rotation (28 infrastructure secrets) | Operator | Pending |
| 3 | Execute T3 rotation (173 service secrets) | Operator | Pending |
| 4 | Full platform reconvergence | Operator | Pending |
| 5 | Verify all OIDC logins work post-rotation | Operator | Pending |
| 6 | Revoke Gitea API token and update remote | Operator | Pending |
| 7 | Add gitleaks rule for inline secrets in Markdown | Next session | Pending |
| 8 | Build `pre_publish_audit.py` gate script | Next session | Pending |
| 9 | Rotate external tokens at providers (Hetzner, Tailscale, etc.) | Operator | Pending |
| 10 | Firewall audit given topology exposure | Operator | Pending |
| 11 | Push OIDC secret removal to ServerClaw remote | Operator | Pending |

---

## Artifacts Produced

| Artifact | Path |
|----------|------|
| Initial exposure postmortem | `docs/postmortems/2026-04-11-public-release-secret-exposure.md` |
| This rotation postmortem | `docs/postmortems/2026-04-11-credential-rotation-response.md` |
| ADR 0405 | `docs/adr/0405-emergency-credential-rotation-after-public-release.md` |
| Rotation script | `scripts/emergency_credential_rotation.py` |
| Rotation runbook | `docs/runbooks/emergency-credential-rotation.md` |
| Rotation receipts | `receipts/credential-rotations/` (created on `--apply`) |
