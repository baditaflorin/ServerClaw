# ADR 0385: Decouple Platform from Operator Identity

**Status:** Proposed
**Decision Date:** 2026-04-09
**Concern:** Fork Portability, DRY, Public Release Readiness

---

## Context

The platform already has substantial fork-support infrastructure:

- **ADR 0339** — Reference deployment system with Jinja2 templates, provider
  profiles, and validation (`reference-deployments/`, `scripts/reference_deployment_samples.py`)
- **ADR 0373** — `derive_service_defaults` computes 15–25 variables per service
  from `platform_service_registry` so roles don't repeat boilerplate
- **Filter plugins** — `service_topology_get`, `platform_service_url`,
  `platform_service_host`, `platform_service_port` in
  `plugins/filter/platform_facts.py` and `plugins/filter/service_topology.py`
- **Fork bootstrap runbook** — `docs/runbooks/fork-reference-platform.md`
- **Image catalog** — `config/image-catalog.json`, indirected via `container_image_catalog`

Despite this, **four coupling patterns** prevent a fork from converging without
deep search-and-replace:

| Pattern | Count | Impact |
|---------|-------|--------|
| `hostvars['proxmox_florin']` | 68 files | Every role that reads topology or ports hits one specific hostname |
| `lv3.org` domain literals | 63 config files + service registry | DNS, SSO, TLS, alerts all assume one domain |
| `*-lv3` hostname literals | 52 files (host_group, tasks, templates) | Service placement hardcoded to named VMs |
| Operator-specific values in `all.yml` | ~200 lines | Email addresses, Tailscale IPs, Brevo keys, admin names mixed with platform defaults |

These are **not scattered random hardcoding**. They are four systemic patterns
with clear root causes and clear fixes.

---

## Decision

Fix the four patterns using Ansible's own variable system — no custom lookup
framework needed. Each fix works independently, can be shipped and tested
separately, and preserves full backwards compatibility.

### Fix 1: Replace `hostvars['proxmox_florin']` with an indirection variable

**Root cause:** 68 role defaults and `derive_service_defaults.yml` itself
reference the Proxmox host by name. A fork with host `proxmox_acme` breaks
everywhere.

**Fix:** Define one variable that resolves to the topology host:

```yaml
# inventory/group_vars/all.yml (add near top)
platform_topology_host: "{{ groups['proxmox_hosts'][0] }}"
```

Then replace every `hostvars['proxmox_florin']` with
`hostvars[platform_topology_host]`. This is a mechanical find-and-replace
across 68 files. The variable resolves at runtime to whatever the first
Proxmox host is in the fork's inventory.

**In `derive_service_defaults.yml`** (the highest-leverage single file):

```yaml
# Before:
- ansible.builtin.assert:
    that:
      - "'platform_service_registry' in hostvars['proxmox_florin']"
      - common_derive_service_name in hostvars['proxmox_florin']['platform_service_registry']

# After:
- ansible.builtin.assert:
    that:
      - "'platform_service_registry' in hostvars[platform_topology_host]"
      - common_derive_service_name in hostvars[platform_topology_host]['platform_service_registry']
```

**Scope:** 68 files, mechanical replacement, low risk.
**Test:** Run `ansible-inventory --list` then `make converge-keycloak` against
the existing inventory — behaviour is identical because `groups['proxmox_hosts'][0]`
resolves to `proxmox_florin`.

---

### Fix 2: Extract `platform_domain` and derive all FQDNs from it

**Root cause:** `lv3.org` appears as a string literal in 63+ config files,
service registry DNS/SSO/TLS blocks, and `all.yml`.

**Fix:** Add one variable and make everything derive from it:

```yaml
# inventory/group_vars/all.yml (add near top)
platform_domain: lv3.org
```

Then in `platform_service_registry` (platform_services.yml), replace every
literal FQDN:

```yaml
# Before:
api_gateway:
  dns:
    records:
      - fqdn: api.lv3.org
  proxy:
    public_fqdn: api.lv3.org
  tls:
    domains:
      - api.lv3.org

# After:
api_gateway:
  dns:
    records:
      - fqdn: "api.{{ platform_domain }}"
  proxy:
    public_fqdn: "api.{{ platform_domain }}"
  tls:
    domains:
      - "api.{{ platform_domain }}"
```

Most services follow the pattern `<subdomain>.lv3.org`. A handful use
different patterns (`chat.lv3.org` for ServerClaw, `sso.lv3.org` for
Keycloak). These are already the `public_fqdn` in the registry — just
templatize the domain suffix.

**For `all.yml`** — variables like `proxmox_acme_domain`, `hetzner_dns_zone_name`,
`mail_platform_domain`, `open_webui_admin_email`, etc. all get rewritten
to reference `platform_domain` or a new `platform_operator_email`:

```yaml
# Before:
proxmox_acme_domain: proxmox.lv3.org
hetzner_dns_zone_name: lv3.org
mail_platform_domain: lv3.org
open_webui_admin_email: ops@lv3.org
proxmox_notification_email: baditaflorin@gmail.com

# After:
proxmox_acme_domain: "proxmox.{{ platform_domain }}"
hetzner_dns_zone_name: "{{ platform_domain }}"
mail_platform_domain: "{{ platform_domain }}"
open_webui_admin_email: "{{ platform_operator_email }}"
proxmox_notification_email: "{{ platform_operator_email }}"
```

**For alertmanager rules and Prometheus configs** — these reference FQDNs
for health checks. They should read from the service topology filters
that already exist (`platform_service_url`), or from variables that
derive from `platform_domain`.

**Scope:** ~80 files total (service registry + all.yml + config/).
**Risk:** Medium — FQDN changes affect TLS cert requests, DNS, SSO redirects.
Test with `--check --diff` before live apply.

---

### Fix 3: Replace `*-lv3` hostname literals with `host_group` lookups

**Root cause:** 52 files reference specific VM names like `runtime-control-lv3`,
`postgres-lv3`. The service registry already declares `host_group` per service.
Roles should use it.

**Fix:** The `host_group` field in `platform_service_registry` already maps
each service to its host. The `platform_service_host` filter already exists.
The problem is that many roles bypass the registry and hardcode the hostname.

For **postgres roles** (the biggest cluster — ~20 files), they specify the
target host directly:

```yaml
# Before (in postgres_client tasks):
- community.postgresql.postgresql_query:
    login_host: "{{ hostvars['postgres-lv3'].ansible_host }}"

# After:
- community.postgresql.postgresql_query:
    login_host: "{{ hostvars[playbook_execution_host_patterns.postgres[playbook_execution_env]].ansible_host }}"
```

This already works because `playbook_execution_host_patterns` maps abstract
roles → concrete hosts per environment. It just isn't used consistently.

For **service registry `host_group` fields**, replace literals:

```yaml
# Before:
api_gateway:
  host_group: runtime-control-lv3

# After:
api_gateway:
  host_group: "{{ playbook_execution_host_patterns.runtime_control[playbook_execution_env] }}"
```

**Alternative (simpler):** Keep `host_group` as a literal but define the
hostnames as variables:

```yaml
# inventory/group_vars/all.yml
platform_host_names:
  runtime_control: runtime-control-lv3
  postgres: postgres-lv3
  nginx_edge: nginx-lv3
  # ... etc
```

A fork changes this one map. Roles reference
`platform_host_names.runtime_control` instead of the literal string.

**Scope:** 52 files + service registry.
**Risk:** Low if done as variable indirection. The mapping is 1:1.

---

### Fix 4: Split `all.yml` into platform defaults vs operator identity

**Root cause:** `inventory/group_vars/all.yml` is a ~500-line file that mixes:
- Platform structural defaults (paths, package lists, Proxmox settings)
- Operator identity (`baditaflorin@gmail.com`, `Florin Badita`, `ops@lv3.org`)
- Service-specific configuration (ServerClaw models, One API defaults)
- Deployment-specific network config (Tailscale IPs, management allowed sources)

A fork must read through all 500 lines to find what to change.

**Fix:** Split into three files:

```
inventory/group_vars/all.yml           → platform structural defaults (keep)
inventory/group_vars/all/identity.yml  → operator identity (new)
inventory/group_vars/all/network.yml   → deployment-specific network (new)
```

Ansible merges `group_vars/all/*.yml` automatically — no code changes needed.

**`identity.yml`** contains everything a fork MUST change:

```yaml
# inventory/group_vars/all/identity.yml
# Fork operators: change every value in this file.

platform_domain: lv3.org
platform_operator_email: baditaflorin@gmail.com
platform_operator_name: "Florin Badita"
platform_notification_author: "Proxmox LV3"

# Admin accounts
open_webui_admin_email: "{{ platform_operator_email }}"
open_webui_admin_name: "{{ platform_operator_name }}"
serverclaw_admin_email: "{{ platform_operator_email }}"
serverclaw_admin_name: "{{ platform_operator_name }}"
proxmox_notification_email: "{{ platform_operator_email }}"
proxmox_acme_contact_email: "{{ platform_operator_email }}"
mail_platform_brevo_sender_name: "{{ platform_operator_name }} Mail Bridge"
```

**`network.yml`** contains deployment-specific network layout:

```yaml
# inventory/group_vars/all/network.yml
# Fork operators: adjust to your network topology.

proxmox_management_allowed_sources:
  - 100.64.0.0/10
  - 10.10.10.0/24
  - 90.95.35.115/32

monitoring_influxdb_org: lv3
```

**What stays in `all.yml`:** Everything that works unchanged across forks —
Proxmox package lists, repo URLs, directory path conventions, Ansible settings.

**Scope:** One file split into three. No code changes — Ansible handles the merge.
**Risk:** Extremely low. Ansible's `group_vars/all/` directory support is
standard and well-tested.

---

## Implementation Order

These four fixes are independent. Do them in any order. Suggested sequence
based on risk/reward:

### Step 1: Split `all.yml` (30 minutes, zero risk)

Create `identity.yml` and `network.yml` by moving lines out of `all.yml`.
No variable renames needed. Converge works identically. This immediately
tells fork operators "change this one file."

### Step 2: Add `platform_domain` and `platform_topology_host` (1 hour)

Add two variables to `all.yml`. Don't change any consumers yet.
Verify both resolve correctly:

```bash
ansible -m debug -a "var=platform_domain" proxmox_florin
ansible -m debug -a "var=platform_topology_host" proxmox_florin
```

### Step 3: Replace `hostvars['proxmox_florin']` (2–3 hours, mechanical)

```bash
# Find all occurrences
grep -r "hostvars\['proxmox_florin'\]" \
  collections/ansible_collections/lv3/platform/roles/ \
  --include="*.yml" -l | wc -l
# → 68 files

# Replace (verify diff before committing)
find collections/ansible_collections/lv3/platform/roles/ \
  -name "*.yml" -exec \
  sed -i '' "s/hostvars\['proxmox_florin'\]/hostvars[platform_topology_host]/g" {} +
```

Test one playbook (`make converge-keycloak --check --diff`), then commit.

### Step 4: Templatize `platform_domain` in service registry (2–3 hours)

Replace `lv3.org` literals in `platform_services.yml` with
`{{ platform_domain }}`. Update the 22 alertmanager rule files.
Run `scripts/validate_service_registry.py`.

### Step 5: Extract `platform_host_names` map (1–2 hours)

Define the hostname map in `all.yml`. Update service registry `host_group`
fields. Update the 52 files with hostname literals.

### Step 6: Sweep `all.yml` operator values (1 hour)

Replace remaining operator-specific values (`ops@lv3.org`, `Florin Badita`,
`baditaflorin@gmail.com`, `ServerClaw`, `search.lv3.org`, `chat.lv3.org`)
with references to the identity variables.

**Total estimated effort: 1–2 days of focused work.**

Not 8–12 weeks. Not four phases with sprints. The coupling is systematic
and mechanical — four patterns, four fixes, each independently testable.

---

## What NOT to Do

1. **Don't invent a `config_get()` filter.** Ansible already has layered
   variable resolution (inventory → group_vars → host_vars → role defaults →
   task vars). Adding a custom lookup on top adds complexity without value.

2. **Don't create a `deployment-model.yaml`.** The inventory system IS the
   deployment model. `hosts.yml` + `group_vars/` + `host_vars/` is exactly
   what Ansible provides for this purpose.

3. **Don't abstract the provider layer.** This is a Proxmox platform.
   Abstracting "provider plugins" for AWS/GCP is speculative work with zero
   current users. If someone wants to run this on libvirt, they fork and
   adapt — that's what forks are for.

4. **Don't refactor 74 roles to use a new lookup pattern.** Most roles
   already work correctly through `derive_service_defaults` + service
   registry. The problem is the 4 coupling patterns above, not the role
   architecture.

---

## Validation

After all six steps, verify:

```bash
# Zero direct references to operator hostname
grep -r "hostvars\['proxmox_florin'\]" \
  collections/ansible_collections/lv3/platform/ \
  --include="*.yml" | wc -l
# Expected: 0

# Zero literal domain in service registry
grep -c "lv3\.org" inventory/group_vars/platform_services.yml
# Expected: 0

# Domain is a variable
ansible -m debug -a "var=platform_domain" proxmox_florin
# Expected: lv3.org

# Reference deployment renders with example domain
python scripts/reference_deployment_samples.py validate
# Expected: pass

# Full convergence still works
make converge-keycloak env=production
```

Add a **pre-commit check** (or extend the existing validation gate) that
greps for literal `lv3.org` and `proxmox_florin` in role files and fails
if found. This prevents regression.

---

## What a Fork Operator Does After This

1. `git clone` the repo
2. Edit `inventory/group_vars/all/identity.yml`:
   - Set `platform_domain`, `platform_operator_email`, `platform_operator_name`
3. Edit `inventory/hosts.yml`:
   - Rename hosts, set `ansible_host` IPs for their topology
4. Edit `inventory/host_vars/<their-proxmox-host>.yml`:
   - Set management IP, network bridges, port assignments
5. Populate `.local/` with their secrets
6. `make converge-platform`

Steps 2–4 are **exactly what the existing fork runbook already describes**.
The difference is that after this ADR, step 2 is "change 3 variables in one
file" instead of "grep for lv3.org across 63 files and hope you got them all."

---

## Success Criteria

- [ ] `grep -r "proxmox_florin" collections/ --include="*.yml"` returns 0 hits
- [ ] `grep -r "lv3\.org" inventory/group_vars/platform_services.yml` returns 0 hits
- [ ] `all.yml` split into `all.yml` + `all/identity.yml` + `all/network.yml`
- [ ] Reference deployment validation still passes
- [ ] Full convergence still passes
- [ ] Pre-commit check blocks reintroduction of hardcoded operator values

---

## Related

- ADR 0339 — Reference Deployment System (template infrastructure this builds on)
- ADR 0373 — Service Registry and Derived Defaults
- ADR 0374 — Cross-Cutting Service Declarations
- `docs/runbooks/fork-reference-platform.md`
