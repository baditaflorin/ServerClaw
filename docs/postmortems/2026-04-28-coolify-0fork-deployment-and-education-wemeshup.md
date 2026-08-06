# Postmortem: Coolify 0fork Deployment + education_wemeshup First App Deploy
**Date:** 2026-04-28
**Duration:** ~4 hours across multiple sessions (converges 16–25, then app deployment)
**Author:** Claude (gallant-chebyshev-b0def1 worktree)
**Status:** Resolved — app live at https://education-wemeshup.apps.0fork.com/

---

## Summary

Deploying Coolify to the 0fork Hetzner server took 10 converge iterations (16–25) before reaching `failed=0`. Subsequently, deploying the first application (`education_wemeshup`) to the running Coolify instance required 6 manual steps that **must become IaC** before this workflow can be repeated unattended.

---

## Part 1: Coolify Runtime Converge (runs 16–25)

### Timeline of failures

| Converge | Failure | Root cause |
|----------|---------|------------|
| 16–18 | SSH unreachable | Wrong Proxmox host in inventory (LV3 IP instead of 0fork) |
| 19 | `tmpfs directory missing` | `derive_service_defaults` overwrote `coolify_env_file` to a tmpfs path that wasn't yet created |
| 20 | Bridge subnet mismatch | `172.18.0.0/16` hardcoded in firewall role; Coolify Docker network uses `172.20.0.0/16` |
| 21 | `/api/v1/teams/current` → 404 | `User::create()` skips the Coolify wizard; no `teams` row exists for `team_id=0` |
| 22 | `/api/v1/servers` → empty array | Intermediate fix created team `id=34` but set token `team_id=34`; servers have `team_id=0` |
| 23 | `ModuleNotFoundError: validation_toolkit` | Only the main script was deployed to guests; `validation_toolkit.py` wasn't copied alongside |
| 24 | `cp: cannot create .../debian-base-template/host.fw` | Stale Ansible fact cache (`s1_proxmox-host`) had LV3 hostname; proxmox_security used `{{ ansible_hostname }}` in path |
| 25 | **`ok=216 failed=0`** | All fixes merged |

### Key fixes committed

1. **`coolify_runtime/tasks/main.yml`** — Bootstrap tinker script creates team row with `id=0` via raw `DB::table()->insert()` (bypassing PostgreSQL sequence), then inserts `team_user` pivot row. Token explicitly uses `"team_id" => "0"`.

2. **`repo_deploy_image_cache/tasks/main.yml`** — Added task to copy `validation_toolkit.py` alongside the main helper script on guests.

3. **Fact cache invalidation** — Deleted `.ansible/fact_cache/s1_proxmox-host` to force fresh facts from 65.109.84.223 (`fork-pve-01`).

4. **tmpfs directory creation** — Added explicit `file` task to create the tmpfs mount point before `derive_service_defaults` runs.

5. **Bridge subnet** — Fixed `172.20.0.0/16` in firewall role.

---

## Part 2: education_wemeshup App Deployment

After Coolify was running, deploying `https://github.com/baditaflorin/education_wemeshup` (Go backend + Vite frontend + Postgres, Docker Compose) to `https://education-wemeshup.apps.0fork.com/` required the following manual steps.

### Step-by-step (what was actually done)

1. **Added GitHub deploy key** via `gh api repos/baditaflorin/education_wemeshup/keys` using the Coolify server key already registered in Coolify.

2. **Created Coolify project + environment** via `POST /api/v1/projects` and environment auto-created.

3. **Registered application** via `POST /api/v1/applications/private-deploy-key` with `build_pack: dockercompose`, `docker_compose_location: /compose.yaml`, and initial domain `http://education-wemeshup.apps.0fork.com`.

4. **Triggered deploy** via `POST /api/v1/applications/{uuid}/start` — deployment queued, containers built and started (`postgres → catalog-api → catalog-web` in dependency order).

5. **Patched nginx** on the nginx VM (VM 110) to proxy `*.apps.0fork.com` from `https://10.10.10.71:443` (coolify-apps VM, empty) to `http://10.10.10.70:80` (Coolify Traefik, running).

6. **Fixed domain TLD** — initial deployment used `.0fork.org` (wrong); patched via API PATCH and redeployed to get `.0fork.com` Traefik labels.

7. **Switched to http:// domain** — Coolify's default `https://` domain makes Traefik try HTTP-01 ACME cert validation. Since nginx redirects port 80 → 443, the challenge always 404s and Traefik hangs the HTTPS entrypoint. Switching to `http://` makes Traefik serve on the HTTP entrypoint without TLS; nginx handles TLS externally.

**Result:** `https://education-wemeshup.apps.0fork.com/` returns HTTP 200, serving the Vite frontend.

---

## Part 3: What Must Become IaC

Every manual step above represents a gap in the automation. In priority order:

### P0 — Blocks unattended repeat deploys

#### 1. coolify-apps VM is never bootstrapped as a Coolify server

**Correction from initial analysis:** The nginx template at `publication/templates/proxmox-host.yml:2982` is **already correct** — it looks up `coolify-apps-lv3` by name (`proxmox_guests | selectattr('name', 'equalto', 'coolify-apps-lv3') | map(attribute='ipv4') | first`), not by hardcoded IP. When the IP changes, `make generate-platform-vars` + nginx converge heals it automatically. The template does NOT need to change.

**Actual problem:** `coolify-apps-lv3` (VM 171) has no Traefik on it because `coolify_runtime` never bootstraps it as a Coolify deployment server. The manual nginx patch (`http://10.10.10.70:80`) was a wrong workaround — it will be silently overwritten by the next `make converge-nginx`.

**Fix needed in `coolify_runtime`:** Add a second play targeting `coolify-apps-lv3` that:
1. Installs Docker via the existing `docker_runtime` role
2. Adds `PermitRootLogin yes` + `coolify_deploy_ssh_pubkey` to authorized_keys (variable already defined in defaults/main.yml)
3. Registers coolify-apps as a Coolify server via API call (idempotent check first)
4. Triggers server validation → Coolify installs its own Traefik on coolify-apps

After this runs, `https://coolify-apps-lv3:443` is live, nginx routes correctly, and every IP change is handled by name-based lookup + converge. No hardcoded IPs anywhere.

**Manual patch to revert:** Once coolify-apps is bootstrapped, run `make converge-nginx` to restore the template-generated config. The current live nginx config is temporary and wrong for target state.

#### 2. Traefik cert resolver hardcoded to HTTP-01; DNS-01 needed

**Problem:** `coolify_runtime/templates/docker-compose.yml.j2` hardcodes `--certificatesresolvers.letsencrypt.acme.httpchallenge` (HTTP-01). HTTP-01 is structurally broken when nginx is in front: port 80 redirects to 443, so the ACME challenge response can never be served. Traefik hangs the HTTPS entrypoint indefinitely waiting for a cert.

**Fix needed:** Replace HTTP-01 with DNS-01 via Hetzner DNS (which the platform already uses: `hetzner_dns_zone_id` is in `.local/identity.yml`). Traefik supports `--certificatesresolvers.letsencrypt.acme.dnschallenge.provider=hetzner` with `HETZNER_API_KEY` injected from Vault.

Make this a variable in `coolify_runtime/defaults/main.yml`:
```yaml
coolify_traefik_cert_resolver: dns   # dns or http
coolify_hetzner_dns_api_token_vault_path: "secret/hetzner/dns-api-token"
```

With DNS-01, Traefik on coolify-apps gets real certs for `*.apps.0fork.com` without any dependency on nginx port-80 routing. No manual domain-scheme switching required.

**The `coolify_smoke_domain: http://apps.{{ platform_domain }}`** pattern in defaults/main.yml already shows the correct intent — internal domains use `http://` because nginx handles TLS externally. The `coolify_app_deploy` role must derive domains from `platform_domain` with `http://` scheme for the same reason.

#### 3. SSH access from Coolify container to coolify-apps VM

**Problem:** When adding coolify-apps as a Coolify server, phpseclib SSH fails with "Permission denied (publickey)" even with the correct public key in `authorized_keys`. The sshd default `PermitRootLogin prohibit-password` was blocking root login (required `PermitRootLogin yes`).

**Fix needed:** The `coolify-apps` VM provisioning playbook must:
- Add the Coolify private key's public key to `/root/.ssh/authorized_keys`
- Set `PermitRootLogin yes` in `/etc/ssh/sshd_config`

This is a one-time bootstrap that the `coolify_runtime` role should handle when `coolify_apps_server_ip` is defined.

### P1 — Repeated manual work

#### 4. GitHub deploy key provisioning

**Problem:** For every new private repo, someone must manually add the Coolify server key as a GitHub deploy key.

**Fix needed:** A new role or task in the app-deploy workflow that:
- Checks if the deploy key is already registered (`gh api repos/{owner}/{repo}/keys`)
- Adds it if missing, using the `GITHUB_TOKEN` from the operator's `.local/` credentials

#### 5. App registration and first deploy

**Problem:** The entire sequence (create project → create application → trigger deploy) was done manually via `curl` calls relayed through `qm guest exec`.

**Fix needed:** An Ansible role `coolify_app_deploy` that:
- Accepts `repo_url`, `branch`, `compose_file`, `domain`, `project_name`
- Uses the Coolify API to idempotently create/update the project, environment, application
- Triggers a deploy and waits for `status: finished`
- All API calls proxied through a tunnel task (since Coolify API IP whitelist blocks controller IP)

#### 6. Coolify API IP whitelist

**Problem:** The Coolify API allows only `127.0.0.1,172.20.0.1,65.109.84.223`. The Ansible controller (10.10.10.x) is not in the list, so all API calls during automation had to be relayed through `qm guest exec` (slow, fragile, shell-quoting nightmare).

**Fix needed:** Either:
- Add the controller's IP to `allowed_ips` in the bootstrap tinker script, OR
- Create an SSH tunnel in the Ansible role: `ansible_connection=local`, `local_forward: 18000:10.10.10.70:8000`, then use `localhost:18000` for all API calls.

The tunnel approach is cleaner (no persistent whitelist change) and matches the `ssh_tunnel_host` pattern already in `admin-auth.json`.

### P2 — Architecture debt

#### 7. The `coolify-apps` VM is never initialized

**Problem:** VM 171 (`coolify-apps`) is created by the Proxmox provisioning role but has no services on it. The nginx correctly routes to it, but nothing is listening. The intended architecture (Coolify deploys to coolify-apps, Traefik runs on coolify-apps) is never bootstrapped.

**Fix needed:** `coolify_runtime` should include a second play targeting `coolify-apps-lv3` that:
1. Installs Docker
2. Adds the Coolify public key to root authorized_keys
3. Registers coolify-apps as a Coolify server via API
4. Validates the server (which installs Traefik on coolify-apps)

#### 8. admin-auth.json is stale after 0fork clone

**Problem:** `.local/coolify/admin-auth.json` retained LV3 values (`apps_public_url: https://apps.example.com`, `ssh_tunnel_host: 203.0.113.1`) after the 0fork identity overlay was applied. The converge role does not update this file on re-runs.

**Fix needed:** `coolify_runtime` post-deploy task should regenerate `admin-auth.json` from template using `platform_domain`, `management_ipv4`, and `coolify_api_token_name`.

---

## Root causes summary

| # | Root cause | Category |
|---|------------|----------|
| 1 | `team_id=0` convention undocumented; `User::create()` skips wizard | Coolify internals, one-time |
| 2 | nginx routes to empty VM | Architecture gap |
| 3 | Traefik ACME HTTP-01 behind nginx redirect loop | TLS termination model mismatch |
| 4 | API IP whitelist blocks controller | Security feature, automation friction |
| 5 | No role for app registration via Coolify API | Missing IaC |
| 6 | coolify-apps VM never bootstrapped | Architecture gap |
| 7 | Stale fact cache caused wrong hostname path | Operator hygiene |

---

## What went right

- The Ansible `coolify_runtime` converge architecture (service defaults, tmpfs secrets, bootstrap tinker) is solid and correct.
- The phpseclib insight explained why the key format worked for the existing server but not raw `ssh` — Coolify's SSH is pure PHP, immune to OpenSSH client version issues.
- `qm guest exec` as an API relay channel (bypassing IP whitelist) was a viable workaround.
- The three-container Docker Compose (`postgres → catalog-api → catalog-web`) started correctly in dependency order on first deploy.

---

## Recommended next ADRs

| ADR | Title |
|-----|-------|
| TBD | `coolify_app_deploy` Ansible role — idempotent app registration + deploy via Coolify API |
| TBD | Coolify app TLS model — http-only internal routing, nginx terminates TLS |
| TBD | coolify-apps VM bootstrap — SSH access + server registration in one converge |
| TBD | GitHub deploy key automation for private repos |
