# ADR 0471 — Karakeep Coolify Deployment + Runtime Recovery Protocol

**Date:** 2026-04-29
**Status:** Accepted
**Concern:** app-deployment, coolify, self-hosting

---

## Context

The operator requested deployment of [karakeep](https://github.com/karakeep-app/karakeep)
(self-hosted bookmark manager with AI features) onto the 0fork Coolify instance
(`apps.0fork.org`). During the deployment, two blocking problems surfaced:

1. **Coolify control-plane was down.** The `coolify` container had stopped because
   `/run/lv3-secrets/coolify/runtime.env` was missing — a tmpfs-backed secret file
   that is written by the `coolify_runtime` Ansible role but lost on VM restart when
   no reconverge has run since the reboot. The Tailscale route to the Proxmox host
   (100.64.0.1) was also unreachable, so `make converge-coolify` could not be used
   to self-heal.

2. **`coolify_tool.py` `git_repository` double-prefix bug.** The first deploy of a
   public GitHub repo succeeds because Coolify uses the stored URL verbatim for its
   initial `git clone`. But on every subsequent deploy, Coolify's
   `check_git_if_build_needed` function constructs `https://github.com/` + stored
   value. If the stored value is already `https://github.com/owner/repo`, the
   resulting ls-remote URL becomes doubly-prefixed and git fails with exit 128.

---

## Decision

### 1. Coolify Runtime Recovery Without Ansible

When `make converge-coolify` is unavailable (Tailscale/Proxmox unreachable), the
runtime.env can be reconstructed from the deterministic key-derivation in the
`coolify_runtime` role and the values embedded in the committed
`/opt/coolify/docker-compose.yml` on the VM:

```
APP_KEY   = sha256(root_password + ":app")[:32]
APP_ID    = sha256(root_password + ":appid")[:24]
DB_PASSWORD / REDIS_PASSWORD / PUSHER_*  ← from docker-compose.yml environment:
```

Steps:
1. Compute APP_KEY + APP_ID locally from `.local/coolify/root-password.txt`
2. Read remaining secrets from the committed compose file on the VM
3. SCP the reconstructed `runtime.env` to `/run/lv3-secrets/coolify/`
4. Create `docker-compose.override.yml` marking the `coolify` network as
   `external: true` (the network was created outside Compose after a VM reboot and
   lacks the Compose label that Docker Compose v2 requires)
5. `docker compose -f docker-compose.yml -f docker-compose.override.yml up -d`

This procedure is documented in `docs/runbooks/coolify-runtime-recovery.md`.

### 2. API Token Recovery Without APP_KEY Match

After reconstructing runtime.env, existing Sanctum tokens may be invalid if APP_KEY
differs from the original. Insert a fresh token directly into the Postgres database:

```sql
INSERT INTO personal_access_tokens
  (tokenable_type, tokenable_id, name, token, abilities, team_id, created_at, updated_at)
VALUES
  ('App\Models\User', 1, 'recovery-<date>', sha256('<plaintext>'), '["*"]', 0, NOW(), NOW())
RETURNING id;
-- Bearer token: <id>|<plaintext>
```

The `team_id` must match the root team (ID 0). Update `.local/coolify/admin-auth.json`
with the new token and correct `server_uuid` / `destination_uuid` (these can drift if
the Coolify database was rebuilt).

### 3. `coolify_tool.py` — `git_repository` update suppression

`ensure_application` now omits `git_repository` and `git_branch` from the PATCH
payload when updating an existing app. Rationale:

- Coolify's POST `/api/v1/applications/public` validates that the URL starts with
  `https://`, `http://`, `git://`, or `git@`. So creation requires the full URL.
- Coolify stores and uses the `git_repository` field verbatim in `git ls-remote`
  but prepends `https://github.com/` if the stored value looks like a slug. When a
  full URL is stored, this produces a double-prefix on every rebuild check.
- Once an application is created, updating `git_repository` serves no useful purpose
  and risks overwriting whatever normalised form Coolify stored internally.

### 4. Karakeep Required Environment Variables

Karakeep refuses to start in production without:
- `NEXTAUTH_SECRET`: session signing secret (≥32 random bytes)
- `MEILI_MASTER_KEY`: Meilisearch master key
- `NEXTAUTH_URL`: public-facing URL (`https://karakeep.apps.0fork.org`)

These are set via `POST /api/v1/applications/{uuid}/envs` after app creation and
persisted in `.local/karakeep/secrets.env`.

---

## Consequences

- Karakeep is deployed at `https://karakeep.apps.0fork.org` on the 0fork Coolify
  instance, with three running services: `web`, `meilisearch`, `chrome`.
- The Coolify runtime recovery procedure can now be executed without Ansible or
  Tailscale access (pure SSH via jump host + Docker commands).
- `coolify_tool.py` deployments of public GitHub repos are idempotent across
  re-deploys without the git_repository double-prefix failure.
- The `docker-compose.override.yml` left on the VM (`/opt/coolify/`) should be
  removed after the next successful `make converge-coolify` run, which will restore
  the Coolify compose stack to the canonical state.
