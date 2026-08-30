# ADR 0438: Generic-by-Construction — Generative Cascade IaC

- Status: Proposed
- Implementation Status: Not Started
- Date: 2026-04-23
- Concern: forkability, dry-principle, iac-end-to-end, lint-enforcement
- Tags: refactor, generic-by-default, fork-clone, adr-0409-complement, adr-0437-prerequisite
- Relates to / extends:
  - ADR 0407 (generic-by-default / `.local/` overlay) — established the
    overlay mechanism
  - ADR 0409 (zero-sanitization publication) — eliminated `platform_domain`
    / operator PII / public IP hardcoding; publication pipeline is now a
    no-op defensive safety net. **This ADR (0438) addresses a complementary
    axis that 0409 explicitly did not cover: role-internal prefix hardcoding
    (`lv3-*` SQL role names, systemd unit names, container names, policy
    names).** 0409 fixed the Public/Private sanitization axis; 0438 fixes
    the Per-Fork Customization axis.
  - ADR 0424 (example.org clone) — surfaces the concrete failure modes this
    ADR prevents
  - ADR 0437 (overlay-aware `make bootstrap`) — operator contract layer;
    this ADR is the content-correctness layer underneath it
  - ADR 0373 (`derive_service_defaults` pattern) — extend the derivation
    registry with identity flavors
  - ADR 0359 (declarative PostgreSQL client registry) — template for unified
    cross-role credential naming

---

## Context

ADR 0407 declared the codebase **generic by default**. ADR 0409 went further
and eliminated all operator-identity leakage: `platform_domain`, operator
PII, public IPs were refactored out of committed code and the publish
pipeline became a zero-match defensive safety net (audit 2026-04-23: all
Tier C regex replacements match zero files).

ADR 0409 did not, however, address a second class of hardcoding that lives
inside role defaults, templates, and `!unsafe` blocks: the **role-internal
prefix `lv3-*` / `lv3_*`**. Unlike `platform_domain`, this prefix never
appears in the published repo as a "leak marker" — it's just a perfectly
valid-looking service identifier. But it's baked into 190+ places that need
to change per-fork: SQL role names (`lv3_openbao_connect_all`), systemd
unit names (`lv3-control-plane-restore-drill.timer`), container names
(`lv3-redpanda-data`), Keycloak group paths (`lv3-platform-admins`),
OpenBao policy names (`lv3-service-semaphore-runtime`), Grafana dashboard
UIDs, nginx variable names.

Bootstrapping the 0fork clone surfaced these failures one at a time. Each
fails at runtime (not at publish time), because the published code looks
clean but the roles still assume `platform_sql_prefix == "lv3"`.

### The deeper problem: no generative cascade

Fixing the `lv3_*` prefix is necessary but not sufficient. The broader
structural issue is that **identity, topology, service catalog, and
credential flow are authored in many places** — each requiring manual
coordination when anything changes. Every "fix a new fork failure" cycle
proves the cost: one field change needs to propagate through
`.local/identity.yml` → overrides file → role default → compose template
→ service config → DNS → Keycloak → Grafana → Uptime Kuma.

The end state this ADR commits to: **a handful of root files generate
everything downstream, through a cascade of generators with validation
gates between each tier**. When you change `platform_domain` in one
place, every derived artefact updates coherently, and the pipeline
refuses to proceed if any tier fails its schema / cross-reference /
contract checks.

### The example.org Hetzner box is the acceptance test

The fork clone isn't just a nice-to-have second environment. It is the
end-to-end test that validates the entire cascade. "Green on 0fork from
`git clone` to `status.example.org` all-green" is the binary acceptance
signal. Any code path that passes locally against `example.com` but breaks
on 0fork is evidence of a generic-by-construction hole — and the
lint/contract layer must grow until it catches the hole *before* the
code ships.

### Concrete failures observed on the 2026-04-23 fork bootstrap loop

| # | Symptom | Root cause | Fix class |
|---|---------|------------|-----------|
| 1 | `openbao_postgres_host` defaulted to production's 10.10.10.60 | `hostvars[…initial_primary].ansible_host` resolves via production inventory before overlay | late-bound lookup |
| 2 | `common_openbao_compose_env_openbao_address` pointed at bootstrap-time IP `10.10.10.10` after re-IP | Bootstrap-phase address baked into env defaults | phase-aware address filter |
| 3 | Two roles used different variable names for the same credential file (`openbao_postgres_admin_password_local_file` vs `openbao_postgres_rotator_password_local_file`) | Writer/reader variable divergence | unified credential naming |
| 4 | `proxmox_api_automation_user = "{{ platform_sql_prefix }}-automation@pve"` produced `fork-automation@pve` for a `0fork` deployment whose actual user is `0fork-automation@pve` | `platform_sql_prefix` strips leading digit (valid for SQL identifier); PVE user names have no such restriction | explicit prefix flavor |
| 5 | Dynamic PostgreSQL role `creation_statements` hardcoded `GRANT lv3_openbao_connect_all …` inside `!unsafe` | `!unsafe` disables Jinja; literal prefix unreachable by override | Jinja-escape pattern + lint |
| 6 | Overriding `openbao_local_artifact_dir` alone was insufficient — eight child paths had to be overridden individually | Shard generator (`scripts/ansible_scope_runner.py`) bakes child paths eagerly at shard-render time | shard emits template strings |
| 7 | OpenBao's pg_hba entry was missing — its PostgreSQL user is provisioned by one role and consumed by another | No `platform_postgres_clients` entry for cross-role credential lifecycles | credentials registry expansion |
| 8 | Nomad smoke jobs shipped as two committed `.hcl` files per deployment (`lv3-nomad-smoke-*.nomad.hcl`, `0fork-nomad-smoke-*.nomad.hcl`); fork bootstrap referenced the wrong filename and `copy:` failed | Per-deployment HCL files duplicate the same content with only the prefix swapped — generic-by-construction violation | extract to single in-role Jinja `template:` rendering `{{ platform_identity.config_prefix }}-…` (Phase 2, this session) |
| 9 | `playbooks/nomad.yml` multi-host-group play used a folded-scalar (`>-`) parenthesised ternary for `hosts:`, which `scripts/ansible_scope_runner.py:201` cannot parse — bootstrap aborted before any task ran | Scope-runner regex predates multi-line ternary host expressions | rewrite as single-line ternary; longer term, the scope runner should evaluate via Ansible rather than regex (tracked under Phase 4) |
| 10 | `nomad_oidc_auth` failed `BindName is undefined` on second converge | Nomad CLI `acl binding-rule list -json` returns dicts that omit absent fields (no `BindName` key when type ≠ `role`/`policy`); equality test on the missing key raised | guard with `selectattr('AuthMethod','defined') \| selectattr('BindName','defined')` before equality (general-purpose pattern for any Nomad/Consul list-output reconciler) |
| 11 | `postgres_vm` hard-asserted Windmill schema tables exist before applying pgaudit grants — but Windmill converges *after* postgres in `site.yml`, so the assertion always failed on first run | Cross-role ordering coupling without a "deferred grant" mechanism — `fork-overrides.yml` workaround was to disable pgaudit entirely | replace assertion with `to_regclass` probe + `selectattr` filter; grant tasks loop only over confirmed-existing tables; subsequent converges pick up the rest idempotently |

Audit (ran 2026-04-23, see `workstreams/active/generic-by-construction.yaml`)
surfaced **190+ instances of hardcoded `lv3_*` / `lv3-*` literals** across
role defaults, `!unsafe` blocks, and `.j2` templates. Highlights:

- **4 `!unsafe` SQL-grant statements** hardcoding `lv3_openbao_connect_all`
  (openbao_runtime/defaults/main.yml and the roles/ duplicate). Fixed in
  this session; the pattern is the template for the rest.
- **~120 role defaults** with literal `lv3-*` identifiers: SQL role names,
  systemd unit names, container names, Grafana dashboard UIDs, Keycloak
  group paths, image repo prefixes, Docker volume names.
- **~15 `.j2` templates** with embedded `lv3-` prefixes (Grafana dashboard
  UIDs, nginx location names, compose network names).
- **~50 references** to the fact name `lv3_service_topology` (acceptable
  iff the fact is renamed once; otherwise every consumer has to change).

Companion audit (credential-variable divergence) surfaced a structural
pattern beyond `lv3`: the same credential file is referenced by
**different variable names** in writer vs reader roles. Confirmed case is
`openbao_postgres_admin_password_local_file` (writer) vs
`openbao_postgres_rotator_password_local_file` (reader) — single fork
override only reaches one of them, password goes out of sync, 28P01
auth-failure at runtime. The auditor flagged the same anti-pattern as
likely present across the 40+ postgres-backed service pairs.

The categorical fix is not "rename `lv3_*` to `{{ platform_sql_prefix }}_*`
everywhere" — that already failed, because some callsites need a different
prefix flavor than the one `platform_sql_prefix` provides (failure #4
above). The fix is to make **misuse a lint error** and to give roles a
**richer identity surface** so the correct flavor is always available.

## Decision

Adopt five principles, enforced by lint and contract tests, organised as
a three-tier generative cascade with validation gates between each tier.

### The cascade (three tiers)

**Tier 0 — Root facts (hand-authored, tiny, schema-validated):**

| File | Owns | Schema |
|---|---|---|
| `.local/identity.yml` | domain, operator, network CIDRs, public IPs, Tailscale facts | `config/schemas/identity.schema.json` |
| `.local/host_vars/proxmox-host.yml` | hardware (disks, NICs, BIOS) + guest topology | `config/schemas/proxmox-host.schema.json` |
| `config/platform_service_registry.yml` | service catalog: name, host_group, ports, deps, service_type | `config/schemas/service-registry.schema.json` |
| `inventory/group_vars/platform_postgres.yml` | `platform_postgres_clients` list (ADR 0359) | `config/schemas/postgres-clients.schema.json` |
| `config/platform_credentials.yml` | credential owners/consumers/paths (Phase 3, new) | `config/schemas/credentials.schema.json` |
| `config/subdomain-exposure-registry.json` | public vs private subdomains | existing |
| `config/ansible-execution-scopes.yaml` | playbook dependency graph | existing |

**Gate 0 → 1**: JSON Schema validates every Tier 0 file on each commit.
Cross-reference validator (`scripts/validate_tier0_crossrefs.py`)
enforces: every `platform_postgres_clients[*].service` exists in
`platform_service_registry`; every `platform_credentials[*].owner_role`
exists as a role; every subdomain maps to a service; etc. Any Tier 0
file that doesn't round-trip through schema + crossref fails the
pre-push gate.

**Tier 1 — Derived configuration (generated, committed):**

| Artefact | Generator | Inputs from Tier 0 |
|---|---|---|
| `inventory/hosts.yml` | `scripts/generate_inventory.py` | proxmox-host + service_registry |
| `inventory/group_vars/platform.yml` | `scripts/platform_manifest.py` | identity + proxmox-host |
| `build/platform-manifest.json` | `scripts/platform_manifest.py` | service_registry + subdomain_registry |
| `config/prometheus/file_sd/*.yml` | `scripts/generate_discovery_artifacts.py` | service_registry |
| `config/prometheus/rules/*.yml` | `scripts/generate_slo_rules.py` | service_registry SLO fields |
| `build/onboarding/*` | `scripts/generate_discovery_artifacts.py` | service_registry |
| `docs/adr/.index.yaml` | `scripts/generate_adr_index.py` | ADR frontmatter |

**Gate 1 → 2**: `make check-generated-in-sync` re-runs every Tier 1
generator and diffs against committed output. Any drift fails CI. Each
generator is idempotent: running it twice produces byte-identical output.

**Tier 2 — Deploy-time state (produced by Ansible roles, not committed):**

| Artefact | Role | Inputs from Tier 0/1 |
|---|---|---|
| OpenBao policies + approles | openbao_runtime | platform_identity + platform_credentials |
| Keycloak clients + groups | keycloak_runtime | service_registry + platform_identity |
| Grafana dashboards | monitoring_vm | service_registry |
| DNS records (Hetzner API) | proxmox_network / public edge | subdomain_registry + identity |
| nftables rules | proxmox_network | service_registry host_group |
| `pg_hba.conf` | postgres_vm | platform_postgres_clients + service_registry (ADR 0416) |
| compose files | `*_runtime` roles | service_registry (derive_service_defaults) |

**Gate 2 → live**: verification tasks inside each role assert the live
object matches the desired spec (curl HTTP 200, `psql -c SELECT`, etc.).
These exist today but are uneven — Phase 6 promotes them to a uniform
contract test suite.

### Five enforcement principles

### 1. `platform_identity` — a single identity object with multiple flavors

Today (`inventory/group_vars/all/identity.yml` lines 21, 27):
```yaml
platform_config_prefix: "{{ platform_domain | split('.') | first }}"
platform_sql_prefix:    "{{ platform_config_prefix | regex_replace('^[^a-z_]+', '') }}"
```

Two flavors exposed as top-level scalars. 30+ callsites use
`config_prefix`; 4 use `sql_prefix`. Audit 2026-04-23 found **3 callsites
picking the wrong flavor** — they silently break on a domain whose first
label starts with a digit or contains uppercase:

| Callsite | Current | Should be | Reason |
|---|---|---|---|
| `proxmox_acme_plugin_id` | `sql_prefix` | `config_prefix` | Proxmox storage ID, not a SQL role |
| `proxmox_api_token_role` | `sql_prefix \| capitalize` | `pve_prefix \| capitalize` | PVE role name — PVE regex allows digits mid-string but forbids leading digit |
| `proxmox_notification_endpoint_name` | literal override in `.local/identity.yml` (hand-edited to `fork-ops-email` because `0fork-ops-email` fails PVE regex) | `pve_prefix`-derived default | Workaround masks the missing flavor |
| `proxmox_api_automation_user` | `sql_prefix`-derived (fixed this session to `config_prefix`) | `pve_prefix` | PVE username regex `^[A-Za-z]` forbids leading digits |

Introduce `platform_identity` as a typed dict with **five** flavors:

```yaml
platform_identity:
  domain:        "{{ platform_domain }}"                     # example.org
  config_prefix: "{{ platform_domain | split('.') | first }}"  # 0fork
  sql_prefix:    "{{ config_prefix | regex_replace('^[^a-z_]+','') }}"  # fork
  pve_prefix:    "{{ config_prefix | regex_replace('^[0-9]+','') }}"    # fork (strip LEADING digits only)
  unix_prefix:   "{{ config_prefix | lower | regex_replace('[^a-z0-9_-]','') }}"  # fork
  dns_label:     "{{ config_prefix }}"                       # RFC 1123 (same shape, distinct meaning)
  operator_name:  "…"
  operator_email: "…"
```

Flavor invariants:
- `config_prefix` = first DNS label; unrestricted character set.
- `sql_prefix` = PostgreSQL identifier-safe (needs leading `[a-z_]`).
- `pve_prefix` = Proxmox user-name-safe (needs leading `[A-Za-z]`).
- `unix_prefix` = POSIX user-name-safe (`[a-z_][a-z0-9_-]*`).
- `dns_label` = RFC 1123 label (happens to equal config_prefix today but
  diverges if we ever allow uppercase in domain).

For `example.com`, all five flavors equal `"lv3"` — production callsites
unchanged. For `example.org`: `config_prefix="0fork"`, `sql_prefix="fork"`,
`pve_prefix="fork"`, `unix_prefix="0fork"`, `dns_label="0fork"`.

Derivation lives in a filter plugin
(`collections/ansible_collections/lv3/platform/plugins/filter/platform_identity.py`)
with unit tests for each flavor × 5 identity samples
(`lv3`, `0fork`, `UPPERCASE`, `with-dashes`, `_underscore`). The existing
top-level vars `platform_config_prefix` / `platform_sql_prefix` become
thin aliases into `platform_identity.*` — no breaking change.

Lint (Phase 1) establishes the correct callsite → flavor binding and
fails any mismatch. The three misbound callsites above are the first
fix candidates.

### 2. Lint: no raw prefix literals in roles

Pre-push gate runs a scanner:

```
# Fails if any of these appear in:
#   collections/ansible_collections/lv3/platform/roles/**/defaults/**
#   collections/ansible_collections/lv3/platform/roles/**/tasks/**
#   collections/ansible_collections/lv3/platform/roles/**/templates/**.j2
#   roles/**
# Patterns:
#   \blv3[_-]\w+   (literal lv3 identifier)
#   \b0fork[_-]\w+ (literal 0fork identifier — reverse of the same bug)
# Escape hatch: a file-local `# generic-lint: allow` comment on the line.
```

A separate scanner specifically targets `!unsafe` blocks and rejects any
known prefix word inside them. The Jinja-escape pattern
`{{ '{{name}}' }}` + Ansible var substitution is the sanctioned mechanism
for mixing OpenBao/templating placeholders with deployment-derived values.

### 3. Unified credential naming across role pairs

Every credential file has **exactly one canonical variable name**, declared
in the role that owns the credential's lifecycle. Reader roles read the
same variable. The naming convention:

```
<service>_<credential_role>_password_local_file
<service>_<credential_role>_password_remote_file
```

Failure #3 concretely: both `openbao_postgres_backend` and `openbao_runtime`
standardise on `openbao_postgres_rotator_password_local_file`. The
divergent `openbao_postgres_admin_password_local_file` becomes an alias
during the transition and is removed in a follow-up.

A new `platform_credentials` registry declares each credential, its owner,
and its consumers — mirroring `platform_postgres_clients`. Contract tests
verify every credential has exactly one owner and ≥1 reader.

### 4. Phase-aware address filter

Introduce `platform_host_address(hostname, phase='steady')` filter. Phase
values: `bootstrap` (pre-mesh, pre-re-IP public address), `steady`
(post-converge site-local IP), `mesh` (tailscale). Role defaults that
embed an address declare a phase; the filter resolves at task-time against
inventory + overlay.

Failure #2 concretely: `common_openbao_compose_env_openbao_address`
becomes `"http://{{ 'runtime-control' | platform_host_address('steady') }}:8201"`
instead of a literal IP.

### 5. Inventory-shard render keeps `lookup()` results lazy

Root cause (audit 2026-04-23, `platform/ansible/execution_scopes.py`
`render_inventory_shard()` lines 467–512): the shard is built by invoking
`ansible-inventory --yaml`, which **eagerly resolves `lookup()` calls**.
`repo_shared_root` uses `lookup('ansible.builtin.pipe', …)` to shell out
to git, so its value is baked into the shard at render time. That bake
cascades: `repo_shared_local_root` = `{{ repo_shared_root }}/.local`
resolves once, and every downstream path that references
`repo_shared_local_root` carries the baked prefix. Overriding
`repo_shared_local_root` alone in a later overlay does nothing because
the shard already has the resolved absolute path inlined.

Children that reference parents via literal Jinja (e.g.
`openbao_init_local_file: "{{ repo_shared_local_root }}/0fork/openbao/init.json"`
in `fork-overrides.yml`) DO stay lazy — Ansible re-evaluates them at
task time. The bug is specifically at the `lookup()`-boundary level:
once a variable's value comes out of a `lookup`, all its downstream
templates see the resolved string, not the original template.

Fix proposal: teach `render_inventory_shard()` to suppress `lookup()`
resolution on designated variables, so the shard emits
`repo_shared_root: "{{ lookup(…) }}"` as a template string instead of
the resolved path. Concretely, either (a) switch the render to
`ansible-inventory --list --json` with a post-processor that re-inlines
known-lazy variables as template strings, or (b) move
`repo_shared_root` out of inventory entirely and into a
`derive_service_defaults` runtime computation.

Failure #6 concretely: `fork-overrides.yml` drops the 8 per-file
override lines and keeps only the topology-level overrides
(`openbao_legacy_restore_enabled: false`, `openbao_postgres_host: …`).

### 6. Contract tests ("generic-deploy" CI job)

A new CI job runs every playbook in `--check` mode against a synthetic
identity:

```yaml
# tests/fixtures/synthetic-identity.yml
platform_domain: testfork.invalid
platform_operator_name: Test Operator
platform_operator_email: ops@testfork.invalid
```

Any play that references a literal `lv3`, real IPs, real domain, or a
prefix that doesn't round-trip through the synthetic identity fails the
job. This is the structural test that would have caught failures #1, #4,
and #5 before they hit a live fork.

## Consequences

**Positive**

- A new fork operator runs `make bootstrap` once and gets a working
  deployment without chasing per-instance hardcoding.
- Publish-serverclaw sanitization shrinks from ~588 files to near-zero —
  the private and public repos diverge only in `.local/` / `inventory/
  host_vars/` / generated artifacts.
- Adding a new service no longer requires hand-editing four registries
  plus a `.local/*` override file. The identity, credentials, and
  postgres-clients registries are the only sources of truth.
- Pre-push lint prevents regression — literal prefixes can't sneak back in.

**Negative / caveats**

- Significant refactor surface: ~120 defaults files, ~15 templates, and
  the shard generator all change. Phased rollout required (see below).
- Introducing `platform_identity.pve_prefix` / `unix_prefix` / etc. as
  first-class fields requires deciding the flavor semantics up front; a
  wrong choice bakes in a new bug. Mitigation: each flavor has a unit
  test with the inputs `lv3`, `0fork`, `0_digit_start`, `CAPS`, `a-b-c`.
- Contract tests against a synthetic identity catch the common class but
  cannot catch "correct for synthetic, wrong for this specific fork's
  quirks". Live-apply verification on ≥1 non-author fork remains the
  acceptance criterion.

## Implementation Plan

Phased so each phase is independently mergeable and each phase eliminates
a measurable failure class.

### Phase 0 — Stop-the-bleed (now, landed on `claude/gallant-chebyshev-b0def1`)

- [x] Parameterize `openbao_runtime/defaults/main.yml`
  `creation_statements` — use `{{ openbao_postgres_connect_role }}` with
  the Jinja-escape pattern for OpenBao placeholders.
- [x] Fix `proxmox_api_automation_user` to use `platform_config_prefix`
  instead of `platform_sql_prefix`.
- [x] Add openbao to `platform_postgres_clients`.
- [x] Align `openbao_postgres_admin_password_local_file` override.
- [x] Fix `common_openbao_compose_env_openbao_address` to steady-state IP.

### Phase 1 — `platform_identity` object + lint (target: v0.179.0)

- [ ] Write `platform_identity` filter plugin with unit tests for the
      five flavors × five identity samples (`lv3`, `0fork`, `UPPERCASE`,
      `with-dashes`, `_underscore`).
- [ ] Expose `platform_identity` as a derived top-level var in
      `inventory/group_vars/all/identity.yml`; add it to
      `derive_service_defaults` output so every role sees it.
- [ ] Migrate 3 known miscategorized callsites — fixes silent-failure
      class of bug:
      - `proxmox_acme_plugin_id`: `sql_prefix` → `config_prefix`
      - `proxmox_api_token_role`: `sql_prefix | capitalize` → `pve_prefix | capitalize`
      - `proxmox_notification_endpoint_name`: new default using `pve_prefix`,
        remove the hand-edited `.local/identity.yml` override
      - `proxmox_api_automation_user`: `config_prefix` → `pve_prefix`
        (Phase 0 set this to config_prefix as a stopgap).
- [ ] Add pre-push lint: scan for raw `lv3[_-]` / `0fork[_-]` in role
      paths; scan `!unsafe` blocks; fail with per-file allow-comment escape.
- [ ] Add lint binding table (callsite → required flavor) with coverage
      for the 30+ known prefix callsites.

### Phase 2 — Literal prefix sweep (target: v0.180.0)

- [ ] Replace 120+ literal `lv3-*` role-default identifiers with
      `{{ platform_identity.<flavor>_prefix }}-*` — in batches by role
      family (monitoring_*, proxmox_*, openbao_*, *_runtime).
- [x] Replace 4 `!unsafe` SQL grants with the Jinja-escape pattern.
- [ ] Replace 15 template literals.
- [x] Replace duplicated per-deployment Nomad smoke-job HCL files with a
      single in-role Jinja template (failure #8 above): names derive from
      `platform_identity.config_prefix`, fork-overrides drops the
      hand-tuned filename + expected-text overrides.
- [x] Rewrite `playbooks/nomad.yml` multi-host-group `hosts:` from a
      folded-scalar parenthesised ternary to a single-line ternary
      (failure #9 above). Long-term fix tracked under Phase 4 (replace
      regex parser in `scripts/ansible_scope_runner.py` with a real
      Ansible-driven evaluator).
- [x] Add `selectattr('AuthMethod','defined') | selectattr('BindName','defined')`
      guards in `nomad_oidc_auth` reconciliation (failure #10 above).
      Pattern is reusable for any role that diff-reconciles against a
      Nomad/Consul list-output where optional fields may be absent.
- [x] Convert `postgres_vm` pgaudit grants from hard assertion to
      `to_regclass` probe + deferred-grant loop (failure #11 above).
      Removes the cross-role ordering coupling and the
      `postgres_vm_pgaudit_enabled: false` fork-override workaround.
- [ ] Each batch: lint must go green before merge.

### Phase 3 — Unified credential registry (target: v0.181.0)

- [ ] Add `platform_credentials` registry schema + first 10 entries.
- [ ] Reader/writer variable name unification for the openbao_postgres
      rotator pair (model case).
- [ ] Contract test: each declared credential has exactly one owner.
- [ ] Sweep remaining credential variable pairs (~20 estimated).

### Phase 4 — Inventory-shard `lookup()` laziness (target: v0.182.0)

- [ ] Choose resolution path: (a) post-process
      `ansible-inventory --list --json` to re-inline `repo_shared_root`
      et al. as template strings, or (b) move `repo_shared_root` out of
      inventory and derive it in `derive_service_defaults` at task-time.
      Concrete callsite: `platform/ansible/execution_scopes.py`
      `render_inventory_shard()` lines 467–512.
- [ ] Audit every variable currently defined via `lookup(…)` in inventory;
      flag any whose value downstream consumers need to override per-fork.
- [ ] Drop 8 redundant override lines from `playbooks/vars/fork-overrides.yml`.
- [ ] Verify fork bootstrap still converges end-to-end without
      per-artifact-path overrides.

### Phase 5 — `phase_aware_address` filter (target: v0.183.0)

- [ ] Filter plugin + unit tests.
- [ ] Migrate `common_openbao_compose_env_openbao_address` and ~5 other
      known callsites.
- [ ] Add lint for raw IPs in role defaults.

### Phase 6 — Generic-deploy CI job (target: v0.184.0)

- [ ] Synthetic identity fixture.
- [ ] `--check` mode playbook runner in CI.
- [ ] Promote from advisory → required before any future fork work.

## Validation

Per-phase validation is embedded above. Global validation for ADR
acceptance:

1. **Tier 0 schema green**: `scripts/validate_tier0_crossrefs.py` passes
   against every committed root file, in the pre-push gate. Breaks the
   build on any missing cross-reference.
2. **Tier 0 → Tier 1 idempotent**: `make check-generated-in-sync`
   produces byte-identical output on re-run; any drift fails CI.
3. **Lint green on main**: pre-push scanner passes with no allow-comments
   outside of `docs/`, `tests/`, and explicitly-declared exceptions.
4. **Synthetic-identity CI green**: the generic-deploy job passes against
   `testfork.invalid` without any `--extra-vars` overrides.
5. **0fork end-to-end green (the acceptance test)**:
   `PLATFORM_IDENTITY_OVERLAY=.local/identity.yml.0fork make bootstrap`
   on the Hetzner AX41-NVMe from a fresh wipe produces an all-green
   `status.example.org` Uptime Kuma board — **without** any `lv3_*` /
   prefix / credential-path workaround in
   `playbooks/vars/fork-overrides.yml`. The overrides file may retain
   topology-level decisions (`openbao_legacy_restore_enabled: false`,
   Loki MinIO disablement) but every prefix-flavor, credential-path, or
   hardcoded-IP override must be gone.

Once all five gates pass, this ADR moves from Proposed → Accepted and
Implementation Status → Complete. **0fork end-to-end is the binary
acceptance signal.** No partial-credit.

## Open Questions

- Does `platform_identity` belong as a filter plugin, a derived inventory
  var, or both? (Leaning "both" — plugin for correctness, inventory var
  for cheap access.)
- Should the `lv3_service_topology` fact be renamed to
  `platform_service_topology` as part of Phase 2, or left alone? (Leaning
  rename — it's the single biggest-footprint rename and the audit flagged
  50+ callsites.)
- How do we handle existing live deployments where infrastructure objects
  (SQL roles, systemd units, docker volumes) are ALREADY named `lv3-*`?
  Renaming in-place would require data migration. Proposal: keep the
  `lv3-*` names in production but make the generator parameterized so
  new forks get their own prefix. Production's identity literally IS
  `lv3`, so no callsite actually renders wrong for it — only forks need
  the parameterization.
