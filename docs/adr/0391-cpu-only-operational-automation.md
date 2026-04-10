# ADR 0391: CPU-Only Operational Automation — Eliminate AI from Deterministic Work

- Status: Accepted
- Implementation Status: Implemented
- Implemented In Repo Version: 0.178.79
- Implemented In Platform Version: not yet applied
- Implemented On: 2026-04-10
- Date: 2026-04-10
- Concern: Operational Efficiency, Cost Reduction, Determinism, Reliability
- Depends on: ADR 0373 (Service Registry), ADR 0389 (Decommissioning Procedure)
- Tags: automation, cpu-only, operational, cli, contracts, deterministic

## Context

The platform has 344 scripts, 22 validation gates, and rich machine-readable
contracts (service registry, capability catalog, dependency graph, workflow
catalog, version semantics). Despite this, many operational tasks still route
through AI agents that burn GPU tokens on fundamentally **deterministic** work:

- Finding which files reference a service (grep)
- Deciding which playbooks to run after a change (graph traversal)
- Generating removal/addition ADRs (template filling)
- Determining what's affected by a config change (dependency walk)
- Checking service completeness (contract comparison)

### The problem

An AI agent session costs tokens and time even when the task is:
1. **Pattern-matching** — find all X in the codebase
2. **Graph traversal** — what depends on Y?
3. **Template filling** — generate ADR/config from known data
4. **Contract validation** — does Z satisfy its spec?

These are O(n) file operations, not reasoning tasks. Every time we ask an
agent to do them, we pay for intelligence we don't need.

### What already exists (and works)

| Contract / Data Source | File | CPU-queryable? |
|---|---|---|
| Service registry | `inventory/group_vars/all/platform_services.yml` | Yes |
| Service capabilities | `config/service-capability-catalog.json` | Yes |
| Service completeness | `config/service-completeness.json` | Yes |
| Dependency graph | `config/dependency-graph.yaml` | Yes |
| Workflow catalog | `config/workflow-catalog.json` | Yes |
| Version semantics | `config/version-semantics.json` | Yes |
| Secret catalog | `config/secret-catalog.json` | Yes |
| Image catalog | `config/image-catalog.json` | Yes |
| DNS declarations | `config/generated/dns-declarations.yaml` | Yes |
| SSO clients | `config/generated/sso-clients.yaml` | Yes |
| Validation contracts | `config/validation-runner-contracts.json` | Yes |
| Capability contracts | `config/capability-contract-catalog.json` | Yes |
| Integration contracts | `config/integrations/*.yaml` (planned) | Yes |
| Service scaffold template | `roles/_template/service_scaffold/` | Yes |

All of these are JSON/YAML — parseable with zero dependencies beyond
Python's standard library.

### What AI agents still do that could be CPU-only

| Operation | Current | Could be | Blocker |
|---|---|---|---|
| "What references service X?" | Agent runs grep in parallel subagents | `decommission_service.py --service X` | **Done** (this session) |
| "Generate removal ADR" | Agent writes prose | `--generate-adr --reason "..."` | **Done** (this session) |
| "Which playbooks need rerunning after I changed file Y?" | Agent reads dependency graph manually | Script: changed files → affected services → playbook list | **Missing** |
| "What's the impact of removing service X?" | Agent explores codebase | Script: dependency walk + reference count | **Missing** |
| "Is service X complete?" | Agent reads completeness spec | Script: compare service state vs contract | **Exists** (`validate_service_completeness.py`) |
| "Add a new service" | Agent or `scaffold_service.py` | Script only — scaffold already exists | **Mostly done** |
| "What needs reconverging?" | Agent figures it out ad-hoc | Script: diff main..HEAD → affected services → playbook plan | **Missing** |
| "Generate changelog entry" | Agent reads commits + writes prose | Script: git log + template | **Missing** |
| "What validation gates should I run?" | Agent guesses or runs all | Script: changed files → relevant gates | **Missing** |

---

## Decision

### 1. Build `platform_ops.py` — the CPU-only operational CLI

A single entry point that answers operational questions by querying existing
contracts. No network calls, no AI, no tokens.

```bash
# Impact analysis: what depends on this service?
python3 scripts/platform_ops.py impact --service open_webui
# Output: JSON with dependents, consumers, DNS records, OIDC clients, references

# Convergence plan: what needs rerunning after these changes?
python3 scripts/platform_ops.py converge-plan --changed-files inventory/group_vars/all/identity.yml
# Output: ordered list of playbooks to run, with justification

# Convergence plan from git diff:
python3 scripts/platform_ops.py converge-plan --since main
# Output: diff HEAD vs main → affected services → playbook execution order

# Service status: completeness check
python3 scripts/platform_ops.py completeness --service directus
# Output: pass/fail per contract criterion

# Failing services:
python3 scripts/platform_ops.py completeness --failing
# Output: services that don't meet their contracts

# Validation targeting: which gates matter for this change?
python3 scripts/platform_ops.py validation-plan --changed-files roles/directus_runtime/defaults/main.yml
# Output: subset of 22 gates relevant to the change

# Reference scan: where is this service mentioned?
python3 scripts/platform_ops.py references --service open_webui
# Output: grouped file list (same as decommission dry-run but standalone)

# Changelog draft from commits:
python3 scripts/platform_ops.py changelog --since v0.178.77
# Output: templated changelog entries from git log
```

### 2. Data flow: contracts → queries → deterministic answers

```
                  ┌─────────────────────────────┐
                  │   Machine-Readable Contracts │
                  │                              │
                  │  platform_services.yml       │
                  │  dependency-graph.yaml       │
                  │  workflow-catalog.json        │
                  │  service-completeness.json    │
                  │  version-semantics.json       │
                  │  image-catalog.json           │
                  │  secret-catalog.json          │
                  └──────────┬──────────────────┘
                             │
                             ▼
                  ┌──────────────────────────────┐
                  │      platform_ops.py          │
                  │                               │
                  │  Subcommands:                 │
                  │  • impact                     │
                  │  • converge-plan              │
                  │  • completeness               │
                  │  • validation-plan            │
                  │  • references                 │
                  │  • changelog                  │
                  └──────────┬───────────────────┘
                             │
                             ▼
                  ┌──────────────────────────────┐
                  │      JSON output to stdout    │
                  │  (pipeable, machine-readable) │
                  └──────────────────────────────┘
```

### 3. Integrate with existing scripts

`platform_ops.py` does NOT replace existing scripts. It wraps and
orchestrates them:

- `impact` calls → `decommission_service.py` (dry-run) + dependency graph walk
- `converge-plan` calls → `git diff` + dependency graph → workflow catalog lookup
- `completeness` calls → `validate_service_completeness.py` logic
- `validation-plan` calls → file path → role/config classification → gate selection
- `references` calls → `grep` with known service name variants
- `changelog` calls → `git log --format` + template

### 4. Make targets for discoverability

```makefile
ops-impact:         python3 scripts/platform_ops.py impact --service $(SERVICE)
ops-converge-plan:  python3 scripts/platform_ops.py converge-plan --since main
ops-completeness:   python3 scripts/platform_ops.py completeness --failing
ops-validation-plan: python3 scripts/platform_ops.py validation-plan --since main
ops-references:     python3 scripts/platform_ops.py references --service $(SERVICE)
ops-changelog:      python3 scripts/platform_ops.py changelog --since $(SINCE)
```

### 5. Acknowledge limitations

Not everything can be CPU-only. Be explicit about the boundary:

**CPU-only (deterministic):**
- File discovery, reference counting, pattern matching
- Dependency graph traversal, topological sort
- Contract validation (schema comparison)
- Template-based ADR/changelog/config generation
- Convergence ordering (dependency-aware playbook sequencing)
- Impact analysis (what touches what)

**Still needs AI (judgment):**
- Deciding *whether* to remove/add/change a service (policy decision)
- Writing the *reason* for a change (requires understanding context)
- Debugging convergence failures (requires reading error output + reasoning)
- Cross-service troubleshooting (correlating symptoms across subsystems)
- Architecture decisions (trade-off evaluation)
- Interpreting ambiguous user intent

**Quirks and known limitations:**
- Line-level reference removal (`_remove_line_references`) is greedy — it
  removes any line containing the service name. This can over-remove in
  files where the service name appears in unrelated contexts (e.g., a
  service named `api` would match too broadly). Mitigation: the dry-run
  always shows exactly what will change before execution.
- YAML block removal (`_remove_yaml_block`) uses simple indentation heuristics,
  not a full YAML parser. It works for the platform's consistent formatting
  but would break on edge cases like multi-line flow scalars. Mitigation:
  use PyYAML for critical files; accept line-based for the rest.
- The `converge-plan` subcommand's file-to-service mapping relies on path
  conventions (`roles/<service>_runtime/` → service). Services with
  non-standard paths need explicit mapping entries.
- `changelog` generation from git commits produces mechanical summaries,
  not narrative prose. For release notes with context, a human (or AI)
  still adds the "why" after the script generates the "what".

---

## Validation

```bash
# platform_ops.py responds to all subcommands without errors
for cmd in impact converge-plan completeness validation-plan references changelog; do
  python3 scripts/platform_ops.py $cmd --help
done

# Impact analysis returns valid JSON
python3 scripts/platform_ops.py impact --service directus | python3 -m json.tool

# Converge plan returns ordered playbook list
python3 scripts/platform_ops.py converge-plan --since main | python3 -m json.tool

# No AI/network calls in any subcommand (verify with strace/dtruss if needed)
```

---

## Consequences

**Positive:**
- Eliminates GPU token spend on deterministic operations
- Faster execution (grep + graph traversal = seconds vs agent sessions = minutes)
- Deterministic — same input always produces same output
- Auditable — every decision is traceable to a contract or file
- Works offline — no API keys, no network, no model availability dependency
- Composable — JSON output pipes into other tools, CI, or (when needed) AI agents

**Negative / Trade-offs:**
- Maintaining the contracts becomes load-bearing — stale contracts produce
  wrong answers (but validation gates catch staleness)
- The CLI needs updating when new integration surfaces are added
- Mechanical output lacks narrative quality (acceptable — the "what" is
  CPU; the "why" is human or AI)

---

## Implementation Priority

| Subcommand | Effort | Impact | Priority |
|---|---|---|---|
| `references` | Low (grep wrapper) | High (replaces most common agent task) | P0 |
| `impact` | Medium (dependency walk) | High (pre-change analysis) | P0 |
| `converge-plan` | Medium (git diff + graph) | Very High (eliminates ad-hoc convergence) | P0 |
| `completeness` | Low (wraps existing validator) | Medium | P1 |
| `validation-plan` | Medium (file classification) | Medium (faster CI) | P1 |
| `changelog` | Low (git log + template) | Medium | P2 |

---

## Related

- ADR 0373 — Service Registry (the source of truth for service metadata)
- ADR 0389 — Service Decommissioning Procedure (first CPU-only lifecycle automation)
- ADR 0078 — Service Scaffold Generator (CPU-only service creation)
- ADR 0035 — Machine-Readable Execution Contracts (workflow catalog design)
