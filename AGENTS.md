# AGENTS.md

## Purpose

This repository manages a Debian 13 host intended to run Proxmox VE, with
infrastructure changes tracked as code.

Both ChatGPT and Claude may be used in this repo. Work as if another assistant will continue after you.

## Working Rules

1. Leave the repo in a state where another assistant can continue without hidden context.
2. Record important decisions in `docs/adr/`.
3. Record operational procedures in `docs/runbooks/`.
4. Prefer committed automation over ad hoc shell changes on the server.
5. If a manual server change is unavoidable, document it immediately in the same turn.
6. Keep README status and next steps current when the server state materially changes.
7. Run parallel implementation through `workstreams.yaml` and `docs/workstreams/`, not through hidden chat context.
8. One chat thread should normally own one workstream, one branch, and preferably one git worktree.
9. Workstream branches must not rewrite shared release files unless the task is explicitly the integration step.
10. The protected integration files are `VERSION`, release sections in `changelog.md`, canonical observed state in `versions/stack.yaml`, and top-level status summaries in `README.md`.
11. Bump `VERSION` when work is merged to `main`, not for every branch-local change.
12. Bump `platform_version` in `versions/stack.yaml` only when merged work is actually applied live from `main`.
13. Update `changelog.md` whenever `VERSION` changes, and use the `Unreleased` section for merged notes that have not yet been cut into a numbered release.
14. When a live change is actually applied, finish the turn by committing it, pushing it to GitHub, and updating the relevant release/workstream state unless explicitly blocked.
15. Keep everything DRY: centralize shared facts, avoid repeated shell snippets, and refactor duplication early.
16. Keep everything structurally solid: separate concerns, prefer small reversible changes, and do not mix bootstrap, security, storage, and Proxmox object management in one opaque step.
17. Every ADR must record both decision status and implementation state, including the first repo version, first platform version, and date where implementation became true.

## Public Repo Mode

Treat this repository as a forkable reference implementation unless a
workstream explicitly states it is integrating verified live state from the
current deployment.

- Do not commit workstation-specific absolute paths.
- Do not put operator-specific hostnames, domains, IP addresses, or secrets in
  public onboarding surfaces.
- Keep local bootstrap artefacts in ignored `.local/` state or environment
  variables.
- Prefer placeholder, example, or repository-relative values in committed
  documentation and metadata.

## Generic-by-Default Codebase (ADR 0407)

This codebase is designed to be **nearly identical** between the private repo
and the public `github.com/baditaflorin/ServerClaw` repo. Deployment-specific
values live in `.local/` (gitignored), not in committed code.

### The Rule: Generic in Git, Specific in .local/

| What to write | In committed files | In `.local/` |
|--------------|-------------------|--------------|
| Domain references | `example.com` | `.local/identity.yml` has the real domain |
| Operator name/email | `Platform Operator` / `operator@example.com` | `.local/identity.yml` has real values |
| Documentation URLs | `https://grafana.example.com` | Real URLs available via `.local/identity.yml` |
| Test assertions | Use `example.com` in fixtures | Tests that need real values load from `.local/` |
| Ansible role defaults | `{{ platform_domain }}` (template vars) | Resolved at runtime from identity.yml |
| Ansible inventory/config | May use real values (sanitized by publish) | — |
| Secrets, passwords, keys | NEVER committed | `.local/<service>/` directories |

### How Ansible picks up real values at runtime

`platform/ansible/execution_scopes.py` auto-injects `-e @.local/identity.yml`
(Ansible extra-vars, highest precedence) into every playbook run. This means:
- Committed code can use `example.com` or `{{ platform_domain }}`
- At runtime, `platform_domain` resolves to the real domain from `.local/identity.yml`
- Fork operators only edit `.local/identity.yml` — everything else derives from it

### When writing new code

**In roles/templates** — Always use template variables:
```yaml
# GOOD: uses template variable
public_url: "https://grafana.{{ platform_domain }}"

# BAD: hardcodes deployment domain
public_url: "https://grafana.lv3.org"
```

**In docs/tests/workstreams** — Always use `example.com`:
```markdown
# GOOD: generic domain
Visit https://grafana.example.com to view dashboards.

# BAD: deployment-specific domain
Visit https://grafana.lv3.org to view dashboards.
```

**In inventory/config** — Real values are acceptable here (the publish pipeline
sanitizes these ~76 files). But prefer template variables when possible.

### Finding real deployment values

When you need the actual domain, IPs, or operator identity:
1. Read `.local/identity.yml` — has `platform_domain`, `platform_operator_email`, etc.
2. The committed `inventory/group_vars/all/identity.yml` shows the variable structure
3. Never paste values from `.local/` into committed files

## Publication Pipeline (ServerClaw)

This private repo publishes a sanitized copy to the public
`github.com/baditaflorin/ServerClaw` repo. The pipeline is automated —
never manually edit or push to the public repo.

### How it works

1. **Drift audit** — `scripts/audit_sanitization_coverage.py` verifies all
   sensitive values have replacement patterns. Aborts on CRITICAL gaps.
2. **Tier A** — Four deployment-specific files (identity, hosts, operators,
   host_vars) replaced with fork-ready templates from `publication/templates/`.
3. **Tier C** — Regex patterns replace domains, VM names, IPs, and PII across
   remaining text files (~588 files after ADR 0407 generalization).
4. **Leak check** — Scans for leak markers. Aborts if any found.
5. **Force-push** — Commits sanitized snapshot to `serverclaw/main`.

### Commands

| Task | Command |
|------|---------|
| Dry-run (sanitize + leak check, no push) | `make publish-serverclaw` |
| Sanitize + push to public repo | `make publish-serverclaw-push` |
| Check sanitization coverage for drift | `make audit-sanitization` |
| Strict audit (exit 1 on any gap) | `make audit-sanitization-strict` |
| Generalize docs/tests in-place | `python3 scripts/generalize_committed_files.py --apply` |

### When to publish

Run `make publish-serverclaw-push` after merging meaningful changes to `main`.

### When adding new sensitive values

If you add a new VM, operator, public IP, or domain reference:

1. Add the replacement pattern to `config/publication-sanitization.yaml`
2. If the value belongs in a Tier A file, update `publication/templates/`
3. Run `make audit-sanitization` to verify coverage
4. Add a leak marker if the value is CRITICAL (PII, public IP, secret)

### Key files

| File | Purpose |
|------|---------|
| `scripts/publish_to_serverclaw.py` | Publication engine |
| `scripts/audit_sanitization_coverage.py` | Drift detector |
| `scripts/generalize_committed_files.py` | In-place generalization (ADR 0407) |
| `config/publication-sanitization.yaml` | Replacement patterns + leak markers |
| `publication/templates/` | Tier A replacement files (4 files) |

## Deployment Context

- Base OS target: Debian 13
- Hypervisor target: Proxmox VE 9
- Desired management style: infrastructure as code
- Reference topology: dedicated host plus repo-managed guests and services

If a fork is already attached to a live environment, record deployment-specific
facts in the appropriate runtime catalog, receipt, or ignored local overlay
instead of hardcoding them into these onboarding instructions.

## Expectations For Future Changes

When making meaningful infrastructure decisions, update:

- `README.md` only when changing integrated `main` truth
- `docs/adr/`
- `docs/runbooks/`
- `docs/workstreams/` when the change is part of an active workstream
- `workstreams.yaml`
- `VERSION` when merging to `main`
- `changelog.md` when `VERSION` changes
- `versions/stack.yaml` only for merged truth or verified live state
- a Git push if the change was applied live

When adding automation later, prefer a structure like:

- `inventory/`
- `playbooks/`
- `roles/`
- `scripts/`

When implementing automation:

- put shared values in one place
- prefer reusable roles and templates over repeated ad hoc commands
- split responsibilities by concern
- remove duplication when it appears instead of documenting around it

Do not claim the platform is ready for routine production use until:

1. The running OS is confirmed to be the intended fresh Debian 13 install.
2. The bootstrap path is represented in version-controlled automation.
3. The Proxmox security baseline and access model are documented and applied.
4. Routine automation defaults to named non-root identities instead of `root`.

## Agent Onboarding (ADR 0163-0168)

New agent? Read these files in order - all six take under 2 minutes:

1. **README.md** - current platform status and deployment state
2. **AGENTS.md** - this file; rules and conventions
3. **.repo-structure.yaml** - full directory map; find any path instantly
4. **.config-locations.yaml** - where every configuration file lives
5. **docs/adr/.index.yaml** - searchable index of all ADRs by keyword
6. **workstreams.yaml** - parallel work in flight; check before starting

> Token tip: These six reads replace hours of tree exploration.

## Plane Task Board Protocol (ADR 0360)

The **Plane task board** (configured in `.local/plane/`) is the **Agent Work HQ**. Every non-trivial agent session gets a
Plane issue in the **AW** project. This applies to all agents: Claude, Codex,
GPT, Gemini, or any automated script that writes workstream YAML files.

### Session start (any agent)

```bash
# 1. Open a workstream YAML in workstreams/active/<id>.yaml
# 2. Sync it to Plane — creates the AW issue and writes plane_issue_id back:
python scripts/sync_plane_agent_issues.py --workstream <id>
```

### During work — milestone comments

```bash
python scripts/sync_plane_agent_issues.py --workstream <id> \
    --comment "Converge complete. Plane proxy port binding fixed."
```

### On block

Update `status: blocked` in the workstream YAML, then:

```bash
python scripts/sync_plane_agent_issues.py --workstream <id> \
    --comment "Blocked: waiting for postgres migration to complete."
```

### On completion / merge

The workstream close step (updating `status: merged`) triggers a final sync:

```bash
python scripts/sync_plane_agent_issues.py --workstream <id> \
    --comment "Merged to main at <commit>. Live-apply pending."
```

### Rules

- **Git is authoritative.** Plane is a projection. If the Plane task board is down,
  continue without it — the workstream YAML is the fallback.
- `plane_issue_id` is written into the workstream YAML after issue creation.
  Subsequent calls use it directly (no re-scan of the issue list).
- Agents **do not** create issues manually in the Plane UI. The script is the
  only write path so external_id stays canonical.
- Humans can add Plane comments to interact with a running agent. Agents read
  their own issue at session start if `plane_issue_id` is present.
- Skip Plane for single-commit housekeeping (version bumps, manifest regen).

### AW project bootstrap (one-time, already done on this instance)

```bash
python scripts/sync_plane_agent_issues.py --bootstrap-only
# Creates AW project + labels if missing; writes .local/plane/aw-auth.json
```

### Plane Agent Tools (ADR 0363)

Five governed tools for programmatic Plane access via the agent tool registry:

| Tool | Category | Use case |
|------|----------|----------|
| `list-plane-tasks` | observe | List tasks in AW or ADR project, optionally filtered by state |
| `get-plane-task` | observe | Get full details of a single task by UUID |
| `create-plane-task` | execute (approval required) | Create blockers, follow-up tasks, operational findings |
| `update-plane-task` | execute | Update task status, title, priority |
| `add-plane-comment` | execute | Add milestone comments, status notes |

These tools use `.local/plane/admin-auth.json` for credentials and default to the AW project.
Pass `"project": "ADR"` to operate on the architecture decisions project.

---

## Handoff Protocol (ADR 0167)

Follow this before ending any session:

**Starting work:**
- Create a git worktree: `git worktree add .worktrees/<name> main && git checkout -b <branch>`
- Add an entry to `workstreams/active/<id>.yaml` with `status: in_progress`
- Run `python scripts/sync_plane_agent_issues.py --workstream <id>` to register in Plane
- Create `docs/workstreams/adr-XXXX-<name>.md` for major decisions

**During work:**
- Commit frequently with clear messages:
  ```
  [area] Short description

  Purpose: Why this change matters
  Scope: What files changed
  Status: Current state
  Next: What follows
  See also: ADR XXXX
  ```
- New playbooks/roles MUST include metadata header per ADR 0165

**Ending a session:**
- [ ] All work committed, branch pushed to origin
- [ ] `workstreams.yaml` updated with current status
- [ ] Plane issue updated: `python scripts/sync_plane_agent_issues.py --workstream <id> --comment "Session end: <summary>"`
- [ ] README.md updated if deployed state changed
- [ ] Blockers documented in workstreams.yaml if any
- [ ] Receipts created in `receipts/live-applies/` for any live changes
- [ ] If merging to main: bump `VERSION`, update `changelog.md`

**Quick situation table:**

| Situation | Action |
|---|---|
| Starting new work | Create branch + worktree, add to workstreams/active/, sync to Plane |
| Making a change | Commit with Purpose/Scope/Status/Next |
| Infrastructure change | Create receipt in receipts/live-applies/ |
| Major decision | Create ADR in docs/workstreams/ |
| Merging to main | Bump VERSION, update changelog, clear commit |
| Work blocked | Mark status: blocked, document blocker, push branch, sync to Plane |

## Playbook / Role Metadata Standard (ADR 0165)

Every new playbook and role must include a metadata comment block at the top.
Copy from `playbooks/.metadata-template.yml`. Required fields:
- `Purpose` - one sentence
- `Use case` - when to run it
- `Inputs` - required and optional variables
- `Outputs` - what changes on success
- `Idempotency` - safe to re-run? Y/N with explanation
- `Dependencies` - ADRs, roles, prerequisites

## Automated Validation (ADR 0168)

The pre-push gate (`scripts/validate_repo.sh agent-standards`) enforces:
- New playbooks must have `# Purpose:` header
- Branch must appear in `workstreams.yaml`
- `docs/adr/.index.yaml` must be current when ADR files change
  - Regenerate: `uv run --with pyyaml python3 scripts/generate_adr_index.py --write`

## Agent Coordination Patterns (ADR 0347, 0350, 0353, 0355, 0357)

These patterns are **Accepted** and implemented. Use them for all new work.

### File-Domain Locking (ADR 0347) + Apply Serialization (ADR 0355)

Before writing any docker-compose.yml, nginx config, or systemd unit — acquire a lock:

```python
from platform.locking import file_domain_lock, apply_lock, ResourceLockRegistry

registry = ResourceLockRegistry()

# Lock a specific config file (ADR 0347)
with file_domain_lock(registry, vmid="101", role="keycloak_runtime",
                      filename="docker-compose.yml", holder="ws-0347"):
    # safe to write — no other agent can write this file concurrently
    ...

# Lock a full VM apply (ADR 0355) — serializes playbook runs
with apply_lock(registry, vmid="101", holder="ws-0355"):
    # safe to run full playbook against vm:101
    ...
```

Lock key convention: `vm:{vmid}:config:{role}:{filename}` and `vm:{vmid}:apply`

### Service Integration Contracts (ADR 0353)

All cross-service dependencies are declared in `config/integrations/<consumer>--<provider>.yaml`.
Check here **before** changing any service port, database name, or secret path — changing one endpoint can break multiple consumers.

```bash
# Validate all contracts
python3 scripts/validate_integrations.py --check-dead

# Find all consumers of postgres_vm
grep -l "provider: postgres_vm" config/integrations/
```

### Workstream Apply Receipts (ADR 0357)

Guard against duplicate applies and track in-progress state:

```python
from platform.workstream_receipts import WorkstreamApplyReceipts

receipts = WorkstreamApplyReceipts()
receipts.guard_not_completed("ws-0353")   # raises if already applied
receipts.guard_not_in_progress("ws-0353") # raises if another agent is mid-apply

receipt = receipts.start("ws-0353", applied_by="claude/eager-buck", adr="0353")
try:
    # ... do the apply ...
    receipts.complete("ws-0353")
except Exception as e:
    receipts.fail("ws-0353", errors=[str(e)])
```

Receipt files live in `receipts/live-applies/<workstream-id>-apply-receipt.yaml`.

### Nginx Fragment Config (ADR 0350)

To add/update a service's nginx config atomically (write-validate-rename-reload):

```yaml
- name: publish keycloak nginx fragment
  ansible.builtin.include_role:
    name: lv3.platform.nginx_fragment_config
  vars:
    nginx_fragment_service_name: keycloak
    nginx_fragment_content: |
      server {
        listen 443 ssl;
        server_name sso.example.org;
        ...
      }
```

### Change Provenance Tagging (ADR 0351)

All Jinja2 templates must carry a `# managed-by:` header. Add to new templates:

```
# managed-by: role=my_runtime adr=XXXX agent={{ lookup('env','LV3_AGENT_SESSION') | default('operator') }}
```

Audit missing headers: `python3 scripts/check_provenance_headers.py`

---

## Nomad Scheduler (ADR 0232, ADR 0361)

The platform runs a private Nomad cluster for durable batch and long-running
internal jobs. Agents and operators can view, dispatch, and manage jobs.

| Resource | Location |
|---|---|
| **UI** | Nomad scheduler web UI (OIDC login via Keycloak) |
| **API proxy** | Tailscale mesh management proxy (requires management token) |
| **Server** | monitoring-lv3 (see inventory for host details) |
| **Clients** | docker-runtime-lv3, runtime-general-lv3, runtime-ai-lv3, runtime-control-lv3, docker-build-lv3 |
| **CLI wrapper** | `/usr/local/bin/lv3-nomad` on all cluster nodes (auto-loads token) |
| **Playbook** | `playbooks/nomad.yml` |
| **Job definitions** | `config/nomad/jobs/` |
| **Bootstrap token** | `.local/nomad/tokens/bootstrap-management.token` |

**Agent tools:** `list-nomad-jobs`, `get-nomad-job-status`, `dispatch-nomad-job`

When creating or modifying Nomad jobs, place the job spec in `config/nomad/jobs/`
and register it through the Nomad playbook or the `lv3-nomad job run` wrapper.

## Cross-Service Wiring Rules

Some services derive their configuration dynamically from the inventory host list.
After any change to `inventory/hosts.yml` that adds or removes a VM from `lv3_guests`,
re-converge the services below or the running state will drift from inventory truth.

| Trigger | Required follow-up | Why |
|---|---|---|
| VM added to / removed from `lv3_guests` | `make live-apply-service service=realtime` | Netdata child topology derived from `lv3_guests`; new VMs invisible in the realtime monitoring dashboard until Netdata is installed |
| VM added to / removed from `lv3_guests` | `make live-apply-service service=guest-log-shipping` | Loki log-agent topology derived from `lv3_guests`; new VMs produce no log streams until the agent is deployed |

Running `site.yml` (full-stack converge) satisfies all of the above automatically because
`playbooks/groups/observability.yml` imports all topology-tracking service playbooks.
For targeted VM-only runs (`make provision-guests`), apply each service in the table manually afterwards.

## Lessons Learned

- Proxmox guest network identity must be deterministic. Reapplying `qm set --net0 virtio,bridge=...` without an explicit MAC can assign a new MAC address, while Debian 13 cloud-init or systemd-networkd may still match the previous MAC in generated network config. The result is a guest that boots with no usable network even though the intended static config exists.
- For managed guests, pin the MAC address in repo config and keep it stable across reruns. Treat the MAC as part of the guest identity, not as disposable runtime state.
- After changing guest cloud-init inputs such as `net0`, `ipconfig0`, or `cicustom`, refresh the seed data with `qm cloudinit update <vmid>` before restarting the guest. Do not assume `qm set` alone is enough.
- On first boot or early bootstrap, prefer a Proxmox stop/start cycle over `qm reboot` when the guest agent may not be running yet. `qm reboot` can fail with a qga timeout even when the VM itself is otherwise healthy.
- NEVER create symlinks to `.local/` or any credential directory. A symlink named `.local` bypasses `.gitignore` (which only ignores the directory), and committing it destroys the real credential store when checked out. (See ADR 0376.)
- NEVER run `git add .local`, `git add -A`, or `git add .` in any directory containing `.local`. Always name specific files or directories when staging.
- Agents in worktrees do NOT have `.local/` — this is intentional. If credentials are needed, read from the main worktree path directly. Do not create symlinks, copies, or placeholder credentials.
- Never hand-maintain a security boundary list (like sanitization patterns) without an automated audit. The initial publication sanitization config missed 7 of 25 VMs (28% miss rate) and an IPv6 address in a template file. The drift detector (`make audit-sanitization`) catches these gaps automatically.
- Regex patterns for VM names with staging variants need `(-staging)?` optionality — `monitoring-lv3` does NOT match `monitoring-staging-lv3` because `-staging-` is in the middle.
