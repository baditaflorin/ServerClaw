# Postmortem — Karakeep Coolify Deployment (2026-04-29)

**Severity:** P2 — service unavailable, no data loss
**Duration:** ~45 min recovery (Coolify down) + ~20 min deploy iteration
**ADR:** [ADR 0471](../adr/0471-karakeep-coolify-deploy-and-runtime-recovery.md)

---

## What Happened

Operator requested deploying karakeep (a self-hosted bookmark manager) to the 0fork
Coolify instance. Three sequential blockers were encountered and resolved:

1. **Coolify control-plane was down** — `/run/lv3-secrets/coolify/runtime.env` was
   missing on the VM. The Tailscale path to Proxmox was also down, so `make
   converge-coolify` couldn't run. Coolify was manually recovered via SSH jump host.

2. **API token invalid** — After reconstructing the runtime.env with a recomputed
   APP_KEY, existing Sanctum tokens failed. A new token was inserted directly into
   the Postgres DB.

3. **`coolify_tool.py` double-URL bug** — On the second deployment (after setting env
   vars), Coolify's `check_git_if_build_needed` ran `git ls-remote` with a
   double-prefixed URL (`https://github.com/https://github.com/...`) because the tool
   stored the full URL on app creation, and Coolify prepends `https://github.com/`
   again on each subsequent rebuild check.

---

## Root Causes

### RC1: tmpfs secrets lost on VM reboot without re-converge
`/run/lv3-secrets/` is a tmpfs mount. Its contents are written by the Ansible role on
converge. If the VM reboots and a converge doesn't run, the secrets are gone. There is
no persistent fallback for these secrets on the VM itself.

### RC2: Tailscale Proxmox route fragility
The `make converge-coolify` path requires Tailscale connectivity to 100.64.0.1
(the Proxmox host). When that route is down, the entire converge pipeline is
blocked — even for simple service restarts on VMs that are accessible via the
public jump host.

### RC3: `coolify_tool.py` `git_repository` format mismatch
Coolify's API v1 validates that `git_repository` starts with a URL scheme on POST,
but internally Coolify uses the stored value differently in its `git ls-remote`
logic:
- If stored as `owner/repo` → constructs `https://github.com/owner/repo`
- If stored as `https://github.com/owner/repo` → constructs
  `https://github.com/https://github.com/owner/repo` (double-prefix bug)

The tool sent the full URL on both create and update, which worked only on the
first deploy (no ls-remote check). Every subsequent deploy failed.

### RC4: App requires secrets not present at creation time
Karakeep needs `NEXTAUTH_SECRET` and `MEILI_MASTER_KEY` to start. There was no
mechanism in `coolify_tool.py` to inject app-specific secrets at deploy time. The
app started, Coolify reported deployment "finished" (containers up), but the web
service returned HTTP 500 due to missing secrets.

---

## Key Learnings

### 1. "Deployment finished" ≠ "App is healthy"
Coolify's deployment status reflects whether containers started, not whether the
application is serving correctly. A health check on the actual HTTP endpoint
(e.g., `GET /` returning 2xx) should be part of the deploy verification step in
`coolify_tool.py`. Consider adding a `--verify-url` flag that polls the domain
after deployment reports "finished".

### 2. tmpfs secrets are a single-reboot blast radius
Every service that stores secrets in `/run/lv3-secrets/` is one VM reboot away
from being down until converge runs. The converge dependency on Tailscale
amplifies this into a multi-hour outage risk. Mitigations:
- Add a `coolify-secrets-restore.service` systemd unit that writes secrets on
  boot from an encrypted on-disk vault (OpenBao / `.local/` symlink)
- OR: mount a persistent encrypted volume for secrets instead of tmpfs
- At minimum: add a boot-time health check that pages if any secret is missing

### 3. Coolify API v1 has format inconsistencies (git_repository)
The POST validation requires a full URL, but the internal storage/usage expects a
slug. This is a Coolify upstream bug. Workarounds:
- Never update `git_repository` for existing apps in `ensure_application`
- Document this in a comment in the code (already done in this session)
- Consider filing an upstream issue with Coolify

### 4. App-specific secrets should be injected declaratively at deploy time
Currently, secrets (NEXTAUTH_SECRET, etc.) are set manually via API calls after
app creation. This is fragile and easy to forget. The `coolify_tool.py
deploy-repo` command should support a `--env KEY=VALUE` flag (or a `--env-file`)
that calls `POST /api/v1/applications/{uuid}/envs` as part of the deploy flow.
This makes the entire deployment idempotent and self-contained.

### 5. Coolify API token recovery requires DB access
There is no "forgot token" endpoint in Coolify v4. Recovery requires direct DB
access. The recovery procedure (insert hashed token into personal_access_tokens
with team_id=0) should be documented in a runbook and the admin-auth.json should
store both the token AND the approach to regenerate it. Consider: store an
encrypted copy of the DB password in `.local/coolify/` as a recovery mechanism.

### 6. `docker-compose.override.yml` as a runtime patch mechanism
Creating `/opt/coolify/docker-compose.override.yml` with `external: true` for the
pre-existing network was a clean surgical fix that didn't modify the tracked
compose file. This pattern — compose overrides as operator patches — is worth
canonizing. A `coolify-overrides/` directory under `.local/coolify/` could hold
per-VM override files that the `coolify_runtime` role applies if present.

---

## What We Changed

| Fix | Where |
|-----|-------|
| `ensure_application` now omits `git_repository` and `git_branch` from PATCH | `scripts/coolify_tool.py` |
| `repo_for_coolify` for public repos uses full URL (required by Coolify POST validation) | `scripts/coolify_tool.py` |
| Coolify runtime recovery procedure documented | `docs/adr/0466-...` + this postmortem |
| Karakeep secrets persisted | `.local/karakeep/secrets.env` |
| Karakeep deployment receipt saved | `.local/karakeep/deployment-receipt.json` |

---

## What We Didn't Fix (Follow-ups)

- [x] `coolify_tool.py` `deploy-repo` `--env` / `--env-file` flags for declarative secret injection
- [ ] `coolify_tool.py` `--verify-url` post-deploy health check
- [ ] Persistent secrets mount to survive VM reboots without reconverge
- [ ] `make converge-*` fallback path when Tailscale is unreachable (direct SSH)
- [ ] `docs/runbooks/coolify-runtime-recovery.md` (full step-by-step runbook)
- [ ] Karakeep `worker` service (background bookmark crawler) — not yet confirmed running
- [ ] DNS entry for `karakeep.apps.example.org` — confirmed live via `*.apps.example.org` wildcard
- [ ] nginx proxy for `*.apps.example.org` — manually patched to `https://10.10.10.70:443`; needs `make converge-nginx` to persist via Ansible (upstream in `platform.yml` should be `https://10.10.10.70:443` not `https://10.10.10.71:443`)
- [ ] Double SSL termination root cause — nginx Ansible config references `10.10.10.71` (coolify-apps VM, not provisioned); wrong in `platform.yml`; needs correction before next converge
