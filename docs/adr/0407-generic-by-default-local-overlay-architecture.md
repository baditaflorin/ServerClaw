# ADR 0407: Generic-by-Default Codebase with Local Overlay

**Date:** 2026-04-11
**Status:** Accepted
**Supersedes:** Extends ADR 0385 (IoC Library Refactor)

---

## Context

The ServerClaw publish pipeline (`publish_to_serverclaw.py`) applies regex
string replacements to **every text file** in the repository to sanitize
deployment-specific values (`example.com` → `example.com`, real IPs → placeholders,
operator identity → generic). This results in:

- **6,482 files modified** per publish
- **~1 million lines changed** per publish (990,864 additions, 989,243 deletions)
- A massive, unreviable git diff that obscures what actually changed
- A snapshot-based publish model where the entire public repo is rewritten

This is unsustainable. The root cause is that the committed code contains
deployment-specific values (domain, hostnames, operator PII) which must be
regex-scrubbed before publication. ADR 0385 eliminated all deployment-specific
values from Ansible **roles** (0 occurrences of `example.com` in `roles/`), but the
remaining codebase surfaces still contain ~40,900 references across 2,828 files.

### Current reference distribution

| Category | `example.com` hits | Files | Notes |
|----------|---------------|-------|-------|
| roles/ (Ansible) | 0 | 0 | ✅ ADR 0385 complete |
| Jinja2 templates | 1 | 1 | ✅ Trivial |
| scripts/ | 3 | 3 | ✅ Trivial |
| inventory/ | 227 | ~10 | Identity + host_vars |
| config/ YAML | 346 | ~30 | Generated catalogs |
| tests/ | 599 | ~40 | Hardcoded assertions |
| config/ JSON | 995 | ~50 | Generated catalogs |
| .conf files | 1,171 | ~20 | Generated nginx |
| docs/ | 3,988 | ~300 | ADRs, postmortems, workstreams |
| receipts/ | 33,585 | ~2,400 | Deployment evidence |

---

## Decision

**Flip the model**: make the committed codebase **generic by default**
(`example.com`, placeholder IPs, "Platform Operator") and load
deployment-specific values from `.local/` at runtime.

This means:
1. The private repo and public repo become **nearly identical**
2. The publish pipeline shrinks from 6,500 file changes to ~10-50
3. LLMs/agents are instructed to check `.local/` for actual deployment values
4. Fork operators get a working codebase without needing to understand sanitization

### Architecture

```
committed code (git)              .local/ (gitignored, never committed)
├── identity.yml                  ├── identity.yml          ← real domain, operator
│   platform_domain: example.com  │   platform_domain: example.com
│   operator: Platform Operator   │   operator: Platform Operator
├── hosts.yml (generic VMs)       ├── hosts.yml             ← real IPs
├── host_vars/ (template values)  ├── host_vars/            ← real topology
├── config/generated/ (ABSENT)    ├── config/generated/     ← runtime-generated
├── receipts/ (ABSENT)            ├── receipts/             ← deployment evidence
├── docs/ (example.com refs)      └── ssh/, secrets, etc.
└── tests/ (example.com fixtures)
```

**Runtime override mechanism**: Ansible extra-vars (`-e @.local/identity.yml`)
has the highest variable precedence and automatically overrides committed
generic values. The Makefile detects `.local/identity.yml` and injects it.

---

## Phases

### Phase 1: Identity layer flip (immediate, ~1 hour)

**Goal**: Committed `identity.yml` uses `example.com`; real values in `.local/`.

1. Copy current `identity.yml` to `.local/identity.yml`
2. Replace committed `identity.yml` with publication template values
3. Add to Makefile: auto-detect and inject `.local/identity.yml` as extra-vars
4. Update CLAUDE.md: instruct agents to read `.local/identity.yml` for real values
5. Publish pipeline: Tier A replacement for identity.yml becomes a no-op

**Impact**: Eliminates the core identity divergence. Every file that uses
`{{ platform_domain }}` now commits as `example.com`-resolved by default.

**Ansible override mechanism**:
```makefile
# In Makefile — auto-load deployment-specific identity
IDENTITY_OVERRIDE_FILE := $(LOCAL_OVERLAY_ROOT)/identity.yml
ifneq ($(wildcard $(IDENTITY_OVERRIDE_FILE)),)
  IDENTITY_EXTRA_VARS := -e @$(IDENTITY_OVERRIDE_FILE)
endif
```

### Phase 2: Inventory generalization (~1 hour)

**Goal**: Committed inventory uses template values; real hosts in `.local/`.

1. Replace committed `hosts.yml` with publication template
2. Replace committed `host_vars/proxmox-host.yml` with publication template
3. Move real files to `.local/hosts.yml` and `.local/host_vars/proxmox-host.yml`
4. Add to Makefile: load `.local/hosts.yml` as inventory override

**Impact**: Eliminates 227 `example.com` references in inventory.

### Phase 3: Gitignore generated files (~30 minutes)

**Goal**: Generated configs and receipts are not committed.

1. Add to `.gitignore`:
   ```
   config/generated/
   receipts/
   ```
2. Remove currently-committed generated files from git tracking
3. Add `make generate-configs` target that populates `config/generated/`
   from templates using identity values
4. Add `make generate-receipts-dir` for directory scaffold

**Impact**: Eliminates **34,751 references** (995 + 346 + 1,171 + 33,585 from
config/generated, config YAML, .conf files, and receipts). This is the single
biggest win — 85% of all references eliminated.

**Risk**: Scripts that read generated configs need to run `make generate-configs`
first, or fail gracefully with a helpful error.

### Phase 4: Documentation generalization (~4 hours, parallelizable)

**Goal**: Docs use `example.com` in committed files.

1. Run a one-time string replacement across `docs/`:
   `example.com` → `example.com`, hostnames → generic names
2. Update documentation conventions: always use `example.com` when referring
   to deployment URLs; reference `.local/identity.yml` for real values
3. Postmortems and ADRs that describe incidents may keep generic references

**Impact**: Eliminates 3,988 references across ~300 files.

**Risk**: Some historical context in postmortems may be harder to read with
generic domains. Mitigate by adding "Deployment: see `.local/identity.yml`
for real domain" header to docs that reference URLs.

### Phase 5: Test fixture generalization (~2 hours)

**Goal**: Tests use `example.com` fixtures, not real deployment values.

1. Create `tests/fixtures/identity.py` with test constants:
   ```python
   TEST_DOMAIN = "example.com"
   TEST_OPERATOR = "Platform Operator"
   ```
2. Replace hardcoded `example.com` in test files with fixture references
3. Tests that validate real deployment use `.local/` values loaded conditionally

**Impact**: Eliminates 599 references.

### Phase 6: Simplify publish pipeline (the payoff)

**Goal**: Publish pipeline changes ~10-50 files instead of 6,500.

After phases 1-5:
- Tier A file replacements: **mostly no-ops** (committed files already generic)
- Tier C string replacements: **nearly empty** (only catches stragglers)
- Leak check: **still runs** (safety net, but should find nothing)
- Delete paths: **still deletes** private-only files

The publish diff drops from ~1M lines to a few hundred at most.

---

## Consequences

### Positive

- Publish pipeline becomes fast and reviewable (~50 files vs 6,500)
- Private and public repos converge — minimal structural divergence
- Fork operators get a working codebase without sanitization knowledge
- LLMs can work on the committed code without seeing deployment-specific values
  (reducing accidental exposure risk)
- Incremental publishing becomes possible (no more snapshot rebuilds)

### Negative

- Agents/operators must remember to check `.local/identity.yml` for real values
- `make generate-configs` becomes a required step before some operations
- Some documentation loses deployment-specific context (mitigated by headers)
- One-time migration effort (~8 hours total across all phases)

### Neutral

- The `.local/` directory role expands from "secrets only" to "secrets +
  deployment identity + generated artifacts"
- The publish pipeline still exists but becomes much simpler
- Leak markers still needed as a safety net

---

## CLAUDE.md Agent Instructions (to be added)

```markdown
## Deployment-Specific Values

The committed codebase uses generic values (`example.com`, `Platform Operator`,
`203.0.113.x`). Real deployment values live in `.local/`:

- `.local/identity.yml` — real domain, operator name/email
- `.local/hosts.yml` — real host IPs
- `.local/host_vars/` — real topology

When you need the actual deployment domain, IP, or operator identity:
1. Read `.local/identity.yml` first
2. Use committed `identity.yml` only as a structural reference
3. Never hardcode values from `.local/` into committed files
```

---

---

## Addendum: platform.yml Exception and Agent Guard Rules (2026-04-13)

**Related:** ADR 0413 (Service Health Audit) identified that LLM agent sessions
had been confused by the `example.com` generic-by-default pattern, leading to
incorrect assumptions about TLS certificate errors.

### The platform.yml Exception

`inventory/group_vars/platform.yml` is a **generated** file that MUST contain
real deployment values. Unlike all other committed files, it encodes deeply
nested derived structures (DNS targets, management IPs, service topology bitmaps)
that cannot be provided as Ansible extra-vars at runtime.

**Rule:** `platform.yml` must NEVER contain `example.com` or `203.0.113.1`.
If it does, downstream artifacts (TLS certs, DNS records, Tailscale config,
monitoring targets) will be misconfigured.

**How to regenerate:**
```bash
make generate-platform-vars
```

This reads `.local/identity.yml` as a high-priority overlay and bakes real
values into `platform.yml`. Run it whenever:
- `.local/identity.yml` changes
- `inventory/host_vars/proxmox-host.yml` changes
- You see `203.0.113.1` or `example.com` inside `platform.yml`

**How to detect stale platform.yml:**
```bash
grep -c 'example\.com\|203\.0\.113\.' inventory/group_vars/platform.yml
# must return 0; any hit means regenerate immediately
```

### platform_domain Guard in nginx-edge Playbooks

`playbooks/_includes/nginx_edge_publication.yml` contains an `assert` pre-task
that aborts with a clear error if `platform_domain == 'example.com'`:

```yaml
- name: Assert platform_domain is not the generic example.com placeholder
  ansible.builtin.assert:
    that:
      - platform_domain is defined
      - platform_domain != 'example.com'
    fail_msg: >-
      platform_domain is '{{ platform_domain | default('undefined') }}' ...
      Run 'make generate-platform-vars' before running any nginx-edge playbook.
```

This guard fires for ALL 34 service playbooks that use the nginx-edge include.
It prevents accidental TLS cert issuance with `example.com` as the domain.

### Codified Rules for LLM Agents

The following rules are binding for all automated agents (Claude Code, Semaphore
CI, future LLM workers) operating on this codebase:

| Rule | Enforcement |
|------|-------------|
| Never write `example.com` into `inventory/group_vars/platform.yml` | Guard assertion in nginx-edge playbooks |
| Never commit `platform.yml` with placeholder IPs or domains | Pre-commit hook (planned ADR 0414 candidate) |
| Always run `make generate-platform-vars` when changing `.local/identity.yml` | Makefile target + CLAUDE.md instruction |
| TLS errors are NOT caused by `example.com` in code — they are caused by stale `platform.yml` or missing cert SANs | Documented in ADR 0413 post-mortem |
| Do not interpret `example.com` in `docs/`, `tests/`, `inventory/group_vars/all/identity.yml` as a bug — it is intentional | This ADR |
| Do NOT add real domain names to `docs/`, `tests/`, or `roles/defaults/` | CLAUDE.md Section 9 |

### Disambiguation: example.com Appearances That Are Correct vs. Bugs

| Location | `example.com` present | Correct? |
|----------|----------------------|----------|
| `inventory/group_vars/all/identity.yml` | Yes | ✅ Intentional — generic template |
| `docs/adr/*.md`, `docs/postmortems/*.md` | Yes | ✅ Intentional — docs use generic |
| `tests/*.py` | Yes | ✅ Intentional — test fixtures use generic |
| `roles/*/defaults/main.yml` | Yes, via `{{ platform_domain }}` | ✅ Intentional — resolves at runtime |
| `inventory/group_vars/platform.yml` | Yes | ❌ **BUG** — regenerate immediately |
| `roles/*/defaults/main.yml` (hardcoded, not a variable) | Yes | ❌ **BUG** — use `{{ platform_domain }}` |

---

## Artifacts

| Artifact | Path |
|----------|------|
| This ADR | `docs/adr/0407-generic-by-default-local-overlay-architecture.md` |
| Publication sanitization config | `config/publication-sanitization.yaml` |
| Current identity (real) | `inventory/group_vars/all/identity.yml` |
| Publication template | `publication/templates/identity.yml` |
| Publish script | `scripts/publish_to_serverclaw.py` |
| IoC refactor ADR | `docs/adr/0385-ioc-library-refactor.md` |
| platform.yml guard | `playbooks/_includes/nginx_edge_publication.yml` (pre_tasks assert) |
| Related post-mortem | `docs/postmortems/2026-04-13-service-health-audit.md` |
