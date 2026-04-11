# Postmortem: Public Release Secret & Infrastructure Exposure

**Date:** 2026-04-11
**Severity:** CRITICAL
**Status:** Action Required
**Public Repo:** https://github.com/baditaflorin/ServerClaw

---

## Summary

The proxmox_florin_server codebase was published to GitHub as `baditaflorin/ServerClaw` with 3,339 commits of full git history. A preparation commit (`31d24a6cd`) scrubbed identity files and removed some docs with credentials, but:

1. One hardcoded secret was **missed** in the current tree
2. All pre-scrub data is **recoverable from git history** (real domain, email, IPs, operator identity, passwords)
3. The internal IP topology and domain names remain **exposed in current committed files** that were not part of the scrub

---

## Exposure Classification

### TIER 1 — ROTATE IMMEDIATELY (Active Credentials Exposed)

| # | Secret | Location | Exposure | Action |
|---|--------|----------|----------|--------|
| 1 | **Keycloak OIDC client secret** `[REDACTED — rotated]` | `docs/workstreams/ws-0362-semaphore-keycloak-oidc.md:87` | **LIVE on serverclaw/main** — not scrubbed | Regenerate in Keycloak, update `.local/semaphore/oidc-client-secret.txt`, re-converge Semaphore |
| 2 | **Semaphore admin password** `[REDACTED — rotated]` | Git history (commit `147cf950e:SEMAPHORE-SETUP-QUICK-START.md`) | Recoverable from git history | Change Semaphore admin password, update `.local/semaphore/admin-password.txt` |
| 3 | **Gitea API token** `[REDACTED — rotated]` | Local `.git/config` remote URL (not in tree, but if anyone clones with `--mirror`) | Local only — low risk but rotate anyway | Revoke token in Gitea (`ops-gitea` user), create new one, update git remote |

### TIER 2 — ROTATE SOON (Credentials Recoverable from Git History)

| # | Secret | Recovery Method | Action |
|---|--------|----------------|--------|
| 4 | **Operator identity** — `baditaflorin@gmail.com`, `Florin Badita`, Keycloak username `florin.badita` | `git log serverclaw/main -- config/operators.yaml` then checkout prior commit | Consider if this identity exposure is acceptable (likely yes — it's the repo owner's public identity) |
| 5 | **Platform domain** — `lv3.org` with all subdomains | `git log serverclaw/main -- inventory/group_vars/all/identity.yml` | Domain is already public via DNS; no rotation possible, but now explicitly tied to this infrastructure codebase |
| 6 | **Proxmox host SSH** — `root@65.108.75.123` | `git log serverclaw/main -- inventory/hosts.yml` | Ensure SSH root login is disabled or key-only; firewall the Proxmox API port (8006) |
| 7 | **Keycloak admin URL** — `https://auth.lv3.org/admin` | Git history of `SEMAPHORE-SETUP-QUICK-START.md` | Ensure Keycloak admin console is behind IP allowlist or VPN |

### TIER 3 — EXPOSED IN CURRENT TREE (Infrastructure Topology)

These are NOT secrets but reveal internal architecture. They are present in committed files **on the public repo right now**.

| Category | Details | Files |
|----------|---------|-------|
| **Internal IP map** | Full 10.10.10.x topology (20+ IPs mapped to services) | `inventory/host_vars/proxmox_florin.yml`, `inventory/group_vars/platform.yml`, `config/build-server.json`, `config/generated/nginx-upstreams.conf` |
| **Public IP** | `65.108.75.123` (Hetzner), `100.118.189.95` (Tailscale) | `receipts/live-applies/`, `inventory/host_vars/proxmox_florin.yml` |
| **Tailscale IP** | `100.64.0.1` (jump host) | `inventory/group_vars/platform.yml`, workstream docs |
| **Domain name** | `lv3.org` with 30+ subdomains mapped to IPs | `config/generated/dns-declarations.yaml`, `config/certificate-catalog.json`, `config/uptime-kuma/monitors.json`, 250+ files |
| **Service topology** | Complete map of what runs on which VM | `config/generated/nginx-upstreams.yaml`, `config/service-capability-catalog.json` |
| **Secret management structure** | Secret names, paths, rotation workflows | `config/token-inventory.yaml`, `config/controller-local-secrets.json` |
| **Deployment evidence** | Proof of service availability with timestamps | `receipts/live-applies/`, `receipts/subdomain-exposure-audit/` |
| **SSH user** | `ops@10.10.10.30` (build server) | `config/build-server.json` |

### TIER 4 — SECURE (Properly Protected)

| Category | Status |
|----------|--------|
| SSH private keys | In `.local/ssh/` — properly gitignored, never committed |
| `.env` files | Properly gitignored |
| Ansible Vault files | None found in tree |
| Database passwords | All template variables (`{{ var }}`), not hardcoded |
| API tokens | All read from files or env vars at runtime |
| JWT secrets | Generated via `openssl rand`, stored locally |
| OAuth client secrets | All sourced from OpenBao or local files |
| Docker registry creds | Not in repo |
| Cloud provider keys | Not in repo |

---

## Root Cause Analysis

### What went right
1. The architecture uses OpenBao + controller-local secrets correctly — actual credential values were never in the codebase
2. `.local/` directory was never committed (pre-commit hook `block-local-credential-dir` works)
3. `.env` files properly gitignored
4. The publish preparation commit correctly scrubbed `identity.yml`, `operators.yaml`, and `hosts.yml`
5. Pre-commit hooks (gitleaks, detect-private-key) prevented private key commits

### What went wrong
1. **Workstream documentation contained a real secret** — `ws-0362-semaphore-keycloak-oidc.md` had the Keycloak OIDC client secret pasted inline and was missed during the scrub
2. **Full git history was pushed** — all 3,339 commits went to GitHub, making every pre-scrub version of every file recoverable
3. **Infrastructure topology was not scrubbed** — `host_vars/`, `group_vars/platform.yml`, `config/generated/`, `config/build-server.json`, receipts, etc. still contain real IPs and the `lv3.org` domain
4. **No systematic secret scan before publish** — gitleaks was configured but not run as a pre-publish gate against the full tree
5. **Semaphore password deletion was incomplete** — the password was removed from `SEMAPHORE-SETUP-QUICK-START.md` (deleted) but the OIDC secret in the workstream doc was overlooked

---

## Immediate Remediation Checklist

### Phase 1: Credential Rotation (Do Now)

- [ ] **Keycloak OIDC secret** — Regenerate the `semaphore` client secret in Keycloak admin, update `.local/semaphore/oidc-client-secret.txt`, run `make converge-semaphore env=production`
- [ ] **Semaphore admin password** — Change via Semaphore UI or API, update `.local/semaphore/admin-password.txt`
- [ ] **Gitea API token** — Revoke `[REDACTED — rotated]` in Gitea settings for `ops-gitea` user, generate new token, update local git remote URL
- [ ] **Review ALL Keycloak client secrets** — The OIDC secret structure is now known; verify all other client secrets (grafana, ops-portal, agent-hub, etc.) were NOT exposed. They appear to be safe (only template references), but double-check.

### Phase 2: Remove Secret from Current Public Tree

- [ ] Remove `[REDACTED — rotated]` from `docs/workstreams/ws-0362-semaphore-keycloak-oidc.md`
- [ ] Commit and push to `serverclaw` remote

### Phase 3: Git History Rewrite (Important)

The public repo has full history. Anyone can run:
```
git log --all --diff-filter=D --name-only  # find deleted files
git show <old-commit>:<file>                # recover pre-scrub content
```

**Options (pick one):**

**Option A: History rewrite with `git filter-repo`** (recommended if repo is new and has no forks)
```bash
# Install: pip install git-filter-repo
# Remove specific secrets from ALL history:
git filter-repo --replace-text <(cat <<'EOF'
[OIDC-SECRET-REDACTED]==>REDACTED
[SEMAPHORE-PASSWORD-REDACTED]==>REDACTED
operator@example.com==>operator@example.com
example.com==>example.com
0.0.0.0==>0.0.0.0
EOF
) --force
git push serverclaw main --force
```

**Option B: Fresh repo with squashed history** (cleanest)
```bash
# Create a new orphan branch from current clean state
git checkout --orphan clean-release
git add -A
git commit -m "Initial public release of ServerClaw platform"
git push serverclaw clean-release:main --force
```

**Option C: Accept the exposure** — If the pre-scrub data (domain, email, IPs) is considered public information anyway (the domain resolves publicly, the email is on GitHub profile), the only real concern is the rotated credentials. Once credentials are rotated, historical values are harmless.

### Phase 4: Infrastructure Hardening (Given Topology Exposure)

Since the full internal topology is now public:

- [ ] **Firewall audit** — Verify Proxmox API (8006), build server, internal services are not reachable from the public internet
- [ ] **SSH hardening** — Confirm `root` SSH login to `65.108.75.123` is disabled; only key-based auth with jump host
- [ ] **Keycloak admin** — Put `auth.lv3.org/admin` behind IP allowlist
- [ ] **Tailscale ACLs** — Review that Tailscale node `100.118.189.95` / `100.64.0.1` access is properly scoped
- [ ] **Monitor for scanning** — Watch firewall logs for increased scanning activity against `65.108.75.123` and `lv3.org` subdomains

---

## Files to Scrub from Public Repo (If Doing Option A)

Priority files that still contain real infrastructure data:

```
# Files with real IPs/domain still on serverclaw/main:
inventory/host_vars/proxmox_florin.yml       # full topology
inventory/group_vars/platform.yml            # 143 refs to lv3.org
config/generated/nginx-upstreams.conf        # IP-to-service mapping
config/generated/nginx-upstreams.yaml        # same
config/generated/dns-declarations.yaml       # 36 lv3.org refs
config/generated/sso-clients.yaml            # 15 lv3.org refs
config/build-server.json                     # build server IP
config/certificate-catalog.json              # 147 lv3.org refs
config/uptime-kuma/monitors.json             # 30 lv3.org refs
config/service-capability-catalog.json       # 234 lv3.org refs
config/health-probe-catalog.json             # 52 lv3.org refs
config/command-catalog.json                  # 70 lv3.org refs
config/workflow-catalog.json                 # 137 lv3.org refs
config/slo-catalog.json                      # 25 lv3.org refs
config/dependency-graph.json                 # 44 lv3.org refs
receipts/live-applies/*                      # deployment evidence
receipts/subdomain-exposure-audit/*          # domain enumeration
receipts/https-tls-assurance/*               # TLS probe results
receipts/k6/*                                # load test results
docs/workstreams/ws-0362-*.md                # OIDC secret
```

---

## Prevention Measures

1. **Pre-publish gate** — Before any public push, run:
   ```bash
   gitleaks detect --source . --config .gitleaks.toml --verbose
   grep -r "lv3\.org\|65\.108\.75\|baditaflorin" --include="*.yml" --include="*.yaml" --include="*.json" --include="*.md" .
   ```

2. **Separate public branch** — Maintain a `public` branch that only contains scrubbed commits; never push `main` directly to GitHub

3. **Template everything** — Replace remaining hardcoded `lv3.org` references in config/ and docs/ with `{{ platform_domain }}` template variables

4. **Exclude receipts from public** — Add `receipts/` to a `.github/.gitattributes` export-ignore or maintain them in a separate private repo

5. **History-clean releases** — For public releases, use `git filter-repo` or orphan branches to avoid leaking historical data

---

## Timeline

| Time | Event |
|------|-------|
| Pre-2026-04-11 | Publish preparation commit (`31d24a6cd`) scrubs identity files |
| 2026-04-11 | Repository pushed to `github.com/baditaflorin/ServerClaw` with full history |
| 2026-04-11 | `2cb17da4f` removes Semaphore admin password but misses OIDC secret |
| 2026-04-11 | This audit discovers: 1 live secret, 2 historical secrets, full topology exposure |

---

## Impact Assessment

| Asset | Impact | Likelihood of Exploit |
|-------|--------|----------------------|
| Keycloak OIDC secret | Unauthorized SSO login to Semaphore | **HIGH** — secret is plaintext on public GitHub |
| Semaphore admin password | Admin access to Semaphore | **MEDIUM** — requires git history recovery + password not yet changed |
| Infrastructure topology | Targeted scanning/attacks | **LOW-MEDIUM** — IPs were already discoverable via DNS, but now explicitly mapped |
| Operator identity | Social engineering | **LOW** — already public GitHub profile owner |

---

## Lessons Learned

1. **Scrubbing a live repo is harder than starting clean.** A 3,339-commit history contains too many surfaces to manually audit. Starting with a squashed orphan branch would have been safer.

2. **Documentation is a secret vector.** Workstream docs, setup guides, and runbooks often contain pasted credentials that aren't caught by `.gitignore` or pre-commit hooks focused on key files.

3. **git history is forever.** Deleting a file or changing its contents does not remove the old version. Force-pushing with history rewrite or using an orphan branch is the only way to truly purge.

4. **Infrastructure-as-code repos inherently contain topology.** For public release, consider a two-repo strategy: public code (roles, scripts, tools) + private deployment (inventory, config, receipts).

5. **Automated scanning must be part of the publish workflow.** The existing gitleaks config is good but wasn't run against the full tree before the push.
