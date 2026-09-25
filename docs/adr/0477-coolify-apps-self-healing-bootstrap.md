# ADR 0477 — Coolify-apps self-healing bootstrap: SSH access, DNS-01 cert, and app-deploy role

**Status:** accepted
**Date:** 2026-04-29
**Workstream:** ws-0447-coolify-apps-self-healing

---

## Context

After the 0fork Coolify deployment (converges 16–25, ADR 0340), every new application
deployment required three manual steps that broke on the next converge run:

1. **nginx was patched by hand** to route `coolify.apps.*` → `http://10.10.10.70:80` (the
   Coolify control-plane VM) instead of `https://10.10.10.71:443` (coolify-apps). The
   nginx template (`publication/templates/proxmox-host.yml`) already contains the correct
   `coolify-apps-lv3` lookup — but that upstream was dead because coolify-apps had no
   Traefik on it.

2. **App domains were switched from HTTPS to HTTP** to avoid Traefik's HTTP-01 ACME
   challenge loop: when nginx is in front and redirects port 80 → 443, the ACME challenge
   response can never be served by Traefik, so certificates fail indefinitely.

3. **PermitRootLogin was manually enabled on coolify-apps** so the Coolify control-plane VM
   could SSH in to install and manage Traefik. Without this, Coolify's server validation
   fails immediately after `register-deployment-server`.

None of these patches survive `make converge-coolify` or `make converge-nginx`. Each
subsequent deployment left the platform in a partially broken state until another human
intervened.

A fourth independent problem was found in the same investigation: the Traefik
file-provider dynamic config for the education-wemeshup `/api/` route used backtick
matcher syntax (`Host(\`…\`) && PathPrefix(\`…\`)`). Backtick syntax works in Docker label
providers but is **silently discarded** by Traefik v3's file provider — the route was
parsed but its matchers were dropped, causing every `/api/` request to fall through to the
default 404 handler. This was fixed immediately in the live config and committed as a
separate hotfix (PR #111, `fix(coolify_runtime): use Traefik v3 double-quote syntax`).

---

## Decisions

### D1 — Bootstrap coolify-apps SSH access via `coolify_runtime` role task (t1)

A new tasks file `coolify_runtime/tasks/bootstrap_apps_vm.yml` runs against coolify-apps
**before** the `register-deployment-server` localhost play:

- Ensures `/root/.ssh` exists (mode 0700).
- Installs the Coolify deploy public key into `root`'s `authorized_keys` via
  `ansible.posix.authorized_key` (idempotent; does not overwrite other keys).
- Writes `/etc/ssh/sshd_config.d/95-coolify-control.conf` with a `Match Address`
  directive that permits root key-based login **only from the Coolify control-plane VM's
  IP** (`coolify_apps_vm_ip`, derived from `proxmox_guests` by name lookup). Global
  `PermitRootLogin` remains `prohibit-password` or disabled for all other sources.
- Flushes the sshd handler before returning, so the socket is reloaded before Coolify
  attempts its SSH validation.

**Why `Match Address` instead of a global `PermitRootLogin yes`:** Global root login
expands the attack surface to every host that can reach coolify-apps' SSH port. The
Coolify control-plane VM's IP is fixed and known at converge time. Limiting to that source
IP means that even if the key is stolen, it is only usable from one specific host.

**Why `ansible.posix.authorized_key` instead of raw file write:** Idempotent; handles
comment-based deduplication; does not clobber keys added by other means (e.g., operator's
own key for emergency access).

### D2 — Switch Traefik from HTTP-01 to DNS-01 cert resolution via Hetzner (t2)

Two changes implement DNS-01 support:

**Change 2a — `coolify_runtime/templates/docker-compose.yml.j2`:** The Coolify
control-plane's own Traefik container becomes a reference implementation. When
`coolify_traefik_cert_resolver == 'dns'`, the `--certificatesresolvers.letsencrypt.acme`
block uses `dnschallenge` instead of `httpchallenge`. The `HETZNER_DNS_API_TOKEN`
environment variable is injected into the proxy service container.

**Change 2b — `coolify_runtime/tasks/patch_apps_proxy.yml`:** After Coolify installs
Traefik on coolify-apps during server validation, a post-registration play patches the
Coolify-managed `docker-compose.yml` on coolify-apps:
- Removes `httpchallenge` lines via regex replacement.
- Inserts `dnschallenge` + provider + delay lines after the `acme.storage` line.
- Injects `HETZNER_DNS_API_TOKEN` into the proxy service environment block.
- Restarts the `coolify-proxy` container when any of the three replacements changed.

**Why patch the file after Coolify installs it rather than pre-placing a template:**
Coolify regenerates its docker-compose.yml during server validation and on proxy
updates. If we pre-place a file, Coolify overwrites it. Patching after registration is
the only hook that runs before Traefik starts but after Coolify has written its file.

**Why `coolify_traefik_cert_resolver` as a variable (not hardcoded `dns`):** Operators
who do not use Hetzner DNS or who run in a non-nginx edge environment should be able to
revert to HTTP-01 without forking the role. The default is `dns`; set to `http` to opt
out.

**Why `delaybeforecheck: 10` on the DNS challenge:** DNS propagation takes a few seconds
after the Hetzner API confirms record creation. Without a delay, Let's Encrypt queries
before the TXT record resolves. Ten seconds is sufficient for Hetzner's authoritative
nameservers; the default (0) causes intermittent ACME failures.

### D3 — `coolify_app_deploy` role: container name discovery instead of hardcoded IPs (t3)

A new role `lv3.platform.coolify_app_deploy` deploys one repo-backed application and
configures Traefik routing end-to-end:

1. Calls `coolify_tool.py deploy-repo` (idempotent: creates or updates the application in
   Coolify). `changed_when` on `"status": "deployed"` distinguishes first deploy from
   no-op re-runs.
2. Waits for `status=finished` only when the previous step actually triggered a new
   deployment (skips on no-op re-runs to keep converge fast).
3. For each `coolify_app_deploy_extra_routes` entry, runs `docker ps --filter
   "name=^{service}-"` on the coolify-apps VM (delegated SSH) and captures the current
   container name. Coolify's container naming convention is `{service}-{network_id}-{timestamp}`;
   the filter prefix is stable.
4. Assembles resolved routes (service dict + `_resolved_name` key) and renders a Traefik
   file-provider dynamic config via `traefik-extra-routes.yml.j2`.
5. Writes the rendered config to `coolify_app_deploy_dynamic_config_dir/{{ app_name }}-extra-routes.yml`
   on coolify-apps. Traefik hot-reloads from this directory.

**Why container names via `docker ps` instead of hardcoded IPs:** Container IPs change on
every redeploy and Docker network recreate. Container names are stable within a deployment
lifecycle and resolvable via Docker's internal DNS from Traefik, which is attached to the
same network. This approach requires no IP knowledge and no static inventory entries.

**Why file-provider config instead of Docker labels:** Coolify manages the Docker labels
on its own application containers. Adding labels to `catalog-api` requires Coolify to
apply them, which requires a Coolify API call with specific label syntax. The file-provider
approach is entirely out-of-band from Coolify and survives Coolify redeployments (the file
stays on disk; the new container name is refreshed on next converge).

**Why double-quote syntax in the Traefik template (`Host("…") && PathPrefix("…")`):**
Traefik v3's file-provider YAML parser silently drops content inside backticks. The route
appears in the config but its matchers are empty — it matches everything or nothing, not
the intended rule. Double-quote syntax is the only correct form for file-provider rules.
Docker label providers accept backticks; this difference is not documented prominently and
caused the education-wemeshup 503 incident (see PR #111).

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| **Coolify overwrites Traefik compose on proxy update/restart** | Medium | High — DNS-01 reverts to HTTP-01, certs fail | `patch_apps_proxy.yml` re-applies on every `converge-coolify` run (idempotent regex replacements). Monitor Coolify release notes for compose schema changes. |
| **`HETZNER_DNS_API_TOKEN` absent at converge time** | Low | Medium — DNS-01 patch silently skipped; certs fail on next renewal | `patch_apps_proxy.yml` logs a skip message when token is empty. Pre-push gate validates the env var is set in CI (Hetzner token required in CI secrets). |
| **Container names change after Coolify redeploy** | High | Low — extra routes return 502 until next converge | Self-healing: re-running `make deploy-app` or `make converge-coolify` rediscovers current container names and rewrites the Traefik config. Observed window: until next scheduled converge. |
| **PermitRootLogin from coolify VM IP opens root if coolify VM compromised** | Very Low | High | The `Match Address` is locked to a single private LAN IP. Coolify VM firewall (linux_guest_firewall role) restricts inbound connections. If coolify VM is compromised, the assumption is that the entire control plane is compromised — scope is not meaningfully wider than the existing threat model. |
| **`docker ps --filter name=^{service}-` returns multiple containers (stale stopped containers)** | Low | Low — first result is used; stopped containers appear in `docker ps` only with `--all` | The command does not pass `--all`, so only running containers are returned. If multiple running containers match the prefix, the first (oldest) is used. Coolify should not leave multiple running containers for the same service. |

---

## What self-heals without human intervention

After this ADR is converged:

| Event | Self-healing mechanism |
|-------|----------------------|
| VM IP changes | `make generate-platform-vars` → re-derives `coolify_apps_vm_ip` by name; next converge updates `sshd_config.d/95-coolify-control.conf` |
| Coolify redeployed app (new container names) | `make deploy-app app=<name>` rediscovers names, rewrites Traefik config |
| Coolify overwrites Traefik compose | `make converge-coolify` re-applies DNS-01 patch |
| New app added to catalog | `make deploy-app app=<name>` creates app in Coolify, waits for deploy, writes Traefik config |
| Certificate renewal | Traefik on coolify-apps handles DNS-01 renewal automatically (no nginx involvement) |

Nothing in the normal operational path requires a human to patch nginx, switch URL schemes,
hardcode IPs, or relay API calls.

---

## Alternatives considered

**Alternative: Use Coolify's native domain labels for all services (not file-provider).**
Requires Coolify API calls with per-service domain configuration. Coolify's API does not
expose per-service routing overrides cleanly for Docker Compose multi-service apps. The
file-provider approach is entirely decoupled from Coolify's opinion of routing.

**Alternative: Pre-place Traefik compose on coolify-apps before server registration.**
Coolify unconditionally regenerates its compose file during server validation. Any
pre-placed file is immediately overwritten. The post-registration patch (D2) is the
correct hook.

**Alternative: Use a wildcard `PermitRootLogin yes` with IP allowlisting at the firewall.**
Firewall rules and sshd configuration are different defense layers. `Match Address` in
sshd_config is more portable (works even if firewall rules are flushed during maintenance).
Both are deployed; defense in depth is the correct approach.

---

## Files changed

| File | Change type |
|------|------------|
| `collections/ansible_collections/lv3/platform/roles/coolify_runtime/tasks/bootstrap_apps_vm.yml` | New |
| `collections/ansible_collections/lv3/platform/roles/coolify_runtime/tasks/patch_apps_proxy.yml` | New |
| `collections/ansible_collections/lv3/platform/roles/coolify_runtime/defaults/main.yml` | Modified |
| `collections/ansible_collections/lv3/platform/roles/coolify_runtime/templates/docker-compose.yml.j2` | Modified |
| `collections/ansible_collections/lv3/platform/roles/coolify_app_deploy/` | New role |
| `playbooks/coolify.yml` | Modified |
