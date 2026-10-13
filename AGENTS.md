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
6. Keep canonical state (`versions/stack.yaml`, workstream shards, receipts) current when the server state materially changes. `README.md` is generated: never hand-edit it; regenerate with `make generate-readme` and `make generate-status-docs`.
7. Run parallel implementation through `workstreams.yaml` and `docs/workstreams/`, not through hidden chat context.
8. One chat thread should normally own one workstream, one branch, and preferably one git worktree.
9. Workstream branches must not rewrite shared release files unless the task is explicitly the integration step.
10. The protected integration files are listed in `workstreams/policy.yaml` under `surface_ownership.global_mutable_paths` (for example `VERSION`, `changelog.md`, `workstreams.yaml`), plus `versions/stack.yaml`; touch them only in the integration or release step.
11. Bump `VERSION` when work is merged to `main`, not for every branch-local change.
12. Bump `platform_version` in `versions/stack.yaml` only when merged work is actually applied live from `main`.
13. Update `changelog.md` whenever `VERSION` changes, and use the `Unreleased` section for merged notes that have not yet been cut into a numbered release.
14. When a live change is actually applied, finish the turn by committing it, pushing it to GitHub, and updating the relevant release/workstream state unless explicitly blocked.
15. **All changes to main go through pull requests** (ADR 0419). Push your branch, create a PR via `gh pr create`, wait for CI, then merge via `gh pr merge --squash --delete-branch`. Direct push to main is reserved for emergencies with admin bypass only.
15. Keep everything DRY: centralize shared facts, avoid repeated shell snippets, and refactor duplication early.
16. Keep everything structurally solid: separate concerns, prefer small reversible changes, and do not mix bootstrap, security, storage, and Proxmox object management in one opaque step.
17. Every ADR must record both decision status and implementation state, including the first repo version, first platform version, and date where implementation became true.

## CI Policy

- Use the configured self-hosted Woodpecker CI for public ServerClaw validation.
- Do not add or restore GitHub Actions workflows or depend on GitHub-hosted runners.
- Keep the public branch ruleset's required Woodpecker status check enabled; a
  missing GitHub Actions status is not a reason to weaken merge protection.
- The private source repository may retain its separately governed self-hosted
  Gitea validation workflow; do not confuse that with GitHub-hosted Actions.

## Public Repo Mode

Treat the committed generic files as a forkable reference implementation (the
public ServerClaw mirror is sanitised from this repo by
`scripts/publish_to_serverclaw.py`) unless a workstream explicitly states it is
integrating verified live state from the current deployment.

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
values in hand-written files live in `.local/` (gitignored). The generated
`inventory/group_vars/platform.yml` and some inventory/config files in the
private repo carry real values; the publish pipeline sanitises them.

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

`platform/ansible/execution_scopes.py` injects the selected identity overlay as
`-e @<file>` (Ansible extra-vars, highest precedence) into scoped playbook runs:
`$PLATFORM_IDENTITY_OVERLAY` when set, otherwise `.local/identity.yml`. This means:
- Committed code can use `example.com` or `{{ platform_domain }}`
- At runtime, `platform_domain` resolves to the real domain from `.local/identity.yml`
- Fork operators edit `.local/identity.yml` and, when their topology differs from the reference, the Proxmox host's `.local/host_vars/<host>.yml` and `.local/inventory/hosts.yml` (ADR 0430, ADR 0437) — everything else derives from those

### ⚠️ CRITICAL: platform.yml must contain real IPs in the private repo

`inventory/group_vars/platform.yml` is a **generated** file produced by
`scripts/generate_platform_vars.py`. It contains deeply-nested derived
structures (e.g. `platform_host.management.ipv4`, `platform_dns_records`,
`platform_service_topology`) that are **not flat Ansible variables** — Ansible extra-vars
cannot override nested dict keys, so the `-e @.local/identity.yml` injection
that works for flat vars does NOT fix baked-in nested values.

The generator loads `.local/identity.yml` as the highest-priority overlay so
that the generated `platform.yml` always contains real deployment IPs and
domains. The publish pipeline then sanitises those real values for the public
ServerClaw mirror.

**Rules for every agent and human operator:**

| Situation | Required action |
|-----------|-----------------|
| After any change to `.local/identity.yml` | `make generate-platform-vars` + commit |
| After any change to `inventory/host_vars/<host>.yml` | `make generate-platform-vars` + commit |
| You see `203.0.113.1` inside `inventory/group_vars/platform.yml` | **BUG** — re-run the generator; `.local/identity.yml` was not applied |
| You see `example.com` inside `inventory/group_vars/platform.yml` | **BUG** — re-run the generator |
| Publishing to ServerClaw | Publish pipeline sanitises real values automatically |

**Never** assume that `203.0.113.1` or `example.com` appearing in
`platform.yml` is correct. Those are sanitisation placeholders — they must
not appear in the private repo's generated output. If `.local/identity.yml`
is missing, the generator re-applies the identity overlay recorded under
`platform_generation.identity_overlay` in the existing `platform.yml`; only
when that record is empty does it fall back to committed placeholders, and that
state is broken.

> **Incident reference**: This gap caused `headscale.example.com` to have a DNS
> A record pointing to `203.0.113.1` (a non-routable documentation IP), which
> broke Tailscale VPN for the entire deployment. The fix was to make the
> generator apply `.local/identity.yml` as a high-priority override.

### When writing new code

**In roles/templates** — Always use template variables:
```yaml
# GOOD: uses template variable
public_url: "https://grafana.{{ platform_domain }}"

# BAD: hardcodes deployment domain
public_url: "https://grafana.example.com"
```

**In docs/tests/workstreams** — Always use `example.com`:
```markdown
# GOOD: generic domain
Visit https://grafana.example.com to view dashboards.

# BAD: deployment-specific domain
Visit https://grafana.<your-real-domain> to view dashboards.
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
`github.com/baditaflorin/ServerClaw` repo. The pipeline is scripted (`scripts/publish_to_serverclaw.py`, run by an
operator) — never manually edit or push to the public repo.

### How it works

1. **Drift audit** — `scripts/audit_sanitization_coverage.py` verifies all
   sensitive values have replacement patterns. Aborts on CRITICAL gaps.
2. **Tier A** — The files listed under `file_replacements` in
   `config/publication-sanitization.yaml` (identity, hosts, operators,
   host_vars, capacity-model) are replaced with fork-ready templates from
   `publication/templates/`.
3. **Tier C** — Regex patterns replace domains, VM names, IPs, and PII across
   remaining text files (the dry run prints the sanitized-file count).
4. **Leak check** — Scans for leak markers. Aborts if any found.
5. **Push** — Commits the sanitized snapshot (parented on the public `main`) and
   pushes a publish branch with `--branch <name>`; merge it via PR once the
   required Woodpecker check passes. A direct force-push to `main` cannot satisfy
   that check.

### Commands

| Task | Command |
|------|---------|
| Dry-run (sanitize + leak check, no push) | `make publish-serverclaw` |
| Sanitize + push a publish branch, then merge via PR (`make publish-serverclaw-push` passes no `--branch`, so it force-pushes `main`) | `uv run --with pyyaml python3 scripts/publish_to_serverclaw.py --push --branch <name>` |
| Check sanitization coverage for drift | `make audit-sanitization` |
| Strict audit (exit 1 on WARNING gaps, 2 on CRITICAL gaps) | `make audit-sanitization-strict` |
| Generalize docs/tests in-place | `python3 scripts/generalize_committed_files.py --apply` |

### When to publish

After merging meaningful changes to `main`, run
`uv run --with pyyaml python3 scripts/publish_to_serverclaw.py --push --branch <name>`
and merge the resulting branch via a public PR once Woodpecker passes.

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
| `publication/templates/` | Tier A replacement files (one per `file_replacements` entry) |

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
- `workstreams/active/<id>.yaml` (then regenerate the generated `workstreams.yaml` with `python3 scripts/workstream_registry.py --write`)
- `VERSION` when merging to `main`
- `changelog.md` when `VERSION` changes
- `versions/stack.yaml` only for merged truth or verified live state
- a Git push if the change was applied live

When adding automation, follow the existing layout:

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

New agent? Read these files in order. `workstreams.yaml` is a generated 9k-line registry, so grep it or open `workstreams/active/<id>.yaml` instead of reading it whole:

1. **README.md** - current platform status and deployment state
2. **AGENTS.md** - this file; rules and conventions
3. **.repo-structure.yaml** - generated section map; follow it to `docs/discovery/repo-structure/<section>.yaml` for path detail
4. **.config-locations.yaml** - generated section index; open `docs/discovery/config-locations/<section>.yaml` for exact config locations
5. **docs/adr/.index.yaml** - root ADR manifest; concern, range and status lookups are in the shards under `docs/adr/index/by-concern/`, `by-range/` and `by-status/` (each entry carries a keywords field; grep the shards for keywords)
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

On completion/merge, run the sync below by hand while the shard is still in `workstreams/active/`.
No hook, CI step or script triggers it:

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
  only writer of workstream issues (`external_source=repo_workstream`,
  `external_id=<workstream id>`); the `create-plane-task` tool and
  `scripts/plane_tool.py create-issue` add other issues without that `external_id`.
- Plane comments added by humans are not read back by any script or agent tool, so
  they do not reach a running agent. Agents read
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
- Create a git worktree: `git worktree add -b <branch> .worktrees/<name> main && cd .worktrees/<name>`
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
- [ ] Status updated in `workstreams/active/<id>.yaml`, then `python3 scripts/workstream_registry.py --write` run to regenerate `workstreams.yaml`
- [ ] Plane issue updated: `python scripts/sync_plane_agent_issues.py --workstream <id> --comment "Session end: <summary>"`
- [ ] README.md is a protected integration file: update it only on main (or when the workstream's ownership manifest declares it)
- [ ] Blockers documented in the workstream shard (`workstreams/active/<id>.yaml` notes) and workstream doc; regenerate `workstreams.yaml`
- [ ] Receipts created in `receipts/live-applies/` for any live changes
- [ ] If merging to main: bump `VERSION`, update `changelog.md`

**Quick situation table:**

| Situation | Action |
|---|---|
| Starting new work | Create branch + worktree, add to workstreams/active/, sync to Plane |
| Making a change | Commit with Purpose/Scope/Status/Next |
| Infrastructure change | Create receipt in receipts/live-applies/ |
| Major decision | Create an ADR in docs/adr/ (then regenerate the ADR index) and link a workstream doc in docs/workstreams/ |
| Merging to main | Bump VERSION, update changelog, clear commit |
| Work blocked | Mark status: blocked, document blocker, push branch, sync to Plane |

## Programmatic Wiki Tools (ADR 0346 / ADR 0418)

The platform wiki at `wiki.example.com` (Outline) is managed programmatically.

### Key scripts

| Script | Purpose |
|--------|---------|
| `scripts/outline_tool.py` | CLI for document, collection, and receipt management. Subcommands: `document.publish`, `receipt.publish`, `receipt.backfill`, `bypass.publish`, `changelog.push` |
| `scripts/outline_client.py` | Shared API client + `publish_receipt_to_outline()` utility |
| `scripts/sync_docs_to_outline.py` | Bootstraps and syncs 12 managed collections (ADRs, Runbooks, etc.) |

### Convention: auto-publish receipts

Every script that writes a JSON file to `receipts/` **must** call
`publish_receipt_to_outline(receipt_path)` immediately after writing.
Import it from the shared module:

```python
from outline_client import publish_receipt_to_outline

# ... after writing the receipt:
publish_receipt_to_outline(receipt_path)
```

The function is best-effort and silent on failure (no token, no Outline API, timeout).
It reads credentials from `OUTLINE_API_TOKEN` env var or `.local/outline/api-token.txt`.

### Backfilling historical receipts

```bash
make backfill-receipts-all          # all categories
make backfill-receipts-security     # Security & Compliance
make backfill-receipts-dr           # DR & Backup Status
make backfill-receipts-automation   # Automation Runs
```

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
- Playbook and role YAML files staged for commit must have a `# Purpose:` header (checked against the git index only, so not enforced at pre-push or CI)
- Branch must be registered as a workstream shard (`workstreams/active/` or `archive/`). `workstream-surfaces` fails validation if it is not; `agent-standards` only warns.
- `docs/adr/.index.yaml` must be current when ADR files change
  - Regenerate: `uv run --with pyyaml python3 scripts/generate_adr_index.py --write`

## Pull Request Workflow (ADR 0419 / ADR 0420)

**All changes to main go through pull requests.** This replaces the previous
direct-push-to-main flow and gives every change a reviewable diff, CI
status checks before merge, and a permanent audit trail.

### Standard flow (agents and operators)

```bash
# 1. Work on a branch
git push origin claude/my-branch -u

# 2. Create PR (use [release] prefix for release PRs)
gh pr create --base main --title "[release] Bump to X.Y.Z — summary" --body "..."

# 3. Wait for CI, then merge
gh pr merge <number> --squash --delete-branch
```

### Release PRs vs. feature PRs

- **`[release]` in title**: convention for release PRs. No CI job enforces the
  release-readiness checks (VERSION bump, changelog, release notes, ADR index,
  platform manifest, discovery artifacts); run
  `python3 scripts/check_release_readiness.py --enforce` locally before merging.
- **No `[release]`**: no release-readiness job runs; the Woodpecker pipeline runs
  `validate_repo.sh agent-standards`, which includes a discovery-artifact check.

### Emergency direct push

Admins can bypass branch protection for genuine emergencies:
```bash
SKIP_REMOTE_GATE=1 GATE_BYPASS_REASON_CODE=emergency_hotfix \
  GATE_BYPASS_DETAIL="<describe>" GATE_BYPASS_SUBSTITUTE_EVIDENCE="<passed check or note>" \
  GATE_BYPASS_REMEDIATION_REF="<workstream or issue>" git push origin main
```
Follow up with a retroactive PR or incident note.

### Release-readiness checker

```bash
# Check locally before creating a PR:
python3 scripts/check_release_readiness.py

# Enforce (exit non-zero on failure):
python3 scripts/check_release_readiness.py --enforce
```

## Agent Coordination Patterns (ADR 0347, 0350, 0353, 0355, 0357)

These patterns are **Accepted**. Library or role code exists for each, but the ADRs
are marked 'Not Implemented' and no playbook or role calls the lock or receipt
helpers; do not assume existing playbooks use them. Use them for all new work.

### File-Domain Locking (ADR 0347) + Apply Serialization (ADR 0355)

Before writing any docker-compose.yml, nginx config, or systemd unit — acquire a lock:

```python
from platform.locking import file_domain_lock, apply_lock, ResourceLockRegistry

registry = ResourceLockRegistry()

# Lock a specific config file (ADR 0347)
with file_domain_lock(registry, vmid="101", role="authentik_runtime",
                      filename="docker-compose.yml", holder="ws-0347"):
    # advisory: other agents that also take this lock are blocked; roles and playbooks do not check it
    ...

# Lock a full VM apply (ADR 0355) — serializes playbook runs
with apply_lock(registry, vmid="101", holder="ws-0355"):
    # serialized only against other apply_lock holders on the same vmid
    ...
```

Lock key convention: `vm:{vmid}:config:{role}:{filename}` and `vm:{vmid}:apply`

### Service Integration Contracts (ADR 0353)

Known cross-service dependencies are declared in `config/integrations/<consumer>--<provider>.yaml` (8 contracts; coverage is partial, so also grep `roles/` and inventory).
Check here **before** changing any service port, database name, or secret path — changing one endpoint can break multiple consumers.

```bash
# Validate all contracts
python3 scripts/validate_integrations.py --check-dead

# Find all consumers of postgres_vm
grep -rl "provider: postgres_vm" config/integrations/
```

### Workstream Apply Receipts (ADR 0357)

Guard against duplicate applies and track in-progress state:

```python
from platform.workstream_receipts import WorkstreamApplyReceipts

receipts = WorkstreamApplyReceipts()
receipts.guard_not_completed("ws-0353")   # raises if already applied
receipts.guard_not_in_progress("ws-0353") # raises if an apply is already in_progress in this checkout (receipts are local, not shared across worktrees)

receipt = receipts.start("ws-0353", applied_by="claude/eager-buck", adr="0353")
try:
    # ... do the apply ...
    receipts.complete("ws-0353")
except Exception as e:
    receipts.fail("ws-0353", errors=[str(e)])
```

Receipt files live in `receipts/live-applies/<workstream-id>-apply-receipt.yaml`.

### Nginx Fragment Config (ADR 0350)

To add/update a service's nginx config: the role writes `<name>.conf.new`, runs `nginx -t`, renames it and reloads.
The staged file is outside the `*.conf` include glob, so `nginx -t` does not validate it; validate the fragment separately.

```yaml
- name: publish authentik nginx fragment
  ansible.builtin.include_role:
    name: lv3.platform.nginx_fragment_config
  vars:
    nginx_fragment_service_name: authentik
    nginx_fragment_content: |
      server {
        listen 443 ssl;
        server_name id.example.org;
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
| **UI** | Nomad scheduler web UI (OIDC login via Authentik) |
| **API proxy** | Tailscale mesh management proxy (requires management token) |
| **Server** | monitoring (see inventory for host details) |
| **Clients** | docker-runtime, runtime-general, runtime-ai, runtime-control, docker-build |
| **CLI wrapper** | `/usr/local/bin/<config_prefix>-nomad` (`platform_identity.config_prefix`, derived from the deployment apex domain) on all cluster nodes; it auto-loads the management token only on the Nomad server node `monitoring`, where the token file is mirrored |
| **Playbook** | `playbooks/nomad.yml` |
| **Job definitions** | In-role Jinja templates (e.g. `collections/ansible_collections/lv3/platform/roles/nomad_cluster_bootstrap/templates/nomad-smoke-*.nomad.hcl.j2`) |
| **Bootstrap token** | `.local/nomad/tokens/bootstrap-management.token` |

**Agent tools:** `list-nomad-jobs`, `get-nomad-job-status`, `dispatch-nomad-job`

When creating or modifying Nomad jobs, render them from a single Jinja
template inside the owning role's `templates/` directory and use
`ansible.builtin.template:` (NOT `copy:`) so per-deployment naming derives
from `platform_identity.config_prefix` (ADR 0438). Register the job through
the Nomad playbook or the `{{ platform_identity.config_prefix }}-nomad job run`
wrapper. Do NOT add per-deployment `.hcl` files under `config/nomad/jobs/` —
that pattern was retired by ADR 0438.

## Service VM Migration (ADR 0416 + ADR 0417) — CRITICAL

Moving a service to a different VM touches **three registry fields** that
must stay in sync. Editing any of them manually without the others causes
topology drift and production failures (pg_hba.conf blocks DB connections,
nginx routes to the wrong IP, etc.).

**The single canonical command — no manual registry edits:**

```bash
# Preview: show exactly what will change and which converges will run
make migrate-service-dry-run svc=<service> to=<target-vm>

# Execute: update all registries + ordered converge + write receipt
make migrate-service svc=<service> to=<target-vm> env=production
```

The script rewrites the three fields in one run, but not transactionally: if a later step fails the edits stay in the working tree and must be rolled back with `git checkout`.

| Registry | Field | Authority |
|----------|-------|-----------|
| `inventory/group_vars/all/platform_services.yml` | `host_group` | **AUTHORITATIVE** |
| `inventory/group_vars/all/platform_services.yml` | `proxy.upstream_host` | hand-maintained duplicate of `host_group` — updated by `make migrate-service`, not checked by `validate_topology_consistency.py` |
| `inventory/host_vars/<topology-host>.yml` | `platform_service_topology[svc].owning_vm` | derived — kept in sync |

Then runs converges in the correct dependency order:
`postgres-vm` → `teardown-service (stop old)` → `converge-<svc>` → `nginx-edge`

`converge-<svc>` must already exist as a Make target: check with `grep '^converge-<svc>:' Makefile` before migrating (the script does not check, and it runs after the old container is stopped). The `nginx-edge` step runs `make converge-nginx-edge`, which only reconciles edge certificate SANs and does not change upstreams.

**Why order matters:**
- postgres BEFORE service: pg_hba.conf must allow the new VM before the service starts
- stop-old BEFORE start-new: prevents split-brain (two containers writing to same DB)
- nginx AFTER service: re-render the edge upstreams with `make configure-edge-publication` once the new VM is healthy

**Orphaned container cleanup** (containers left behind by old migrations):

```bash
make detect-orphans   # list containers running on the wrong VM
make purge-orphans    # stop and remove them (SSH-based, requires prod access)
```

**No push-time gate checks registry consistency** — the pre-push hook does not run
`validate_topology_consistency.py`; run it manually (`make migrate-service` runs it as step 1).
Do not rely on the pre-push hook as a backstop; `make migrate-service` is the preventive tool.

**Teardown only** (stop a container without full migration):

```bash
make teardown-service svc=<service> on_vm=<vm> env=production
```

## Cross-Service Wiring Rules

Some services derive their configuration dynamically from the inventory host list.
After adding or removing a VM in `proxmox_guests` (in the Proxmox host's `inventory/host_vars/<host>.yml`) and
regenerating `inventory/hosts.yml` with `make generate-inventory`, re-converge the services below or the running state will drift from inventory truth.

| Trigger | Required follow-up | Why |
|---|---|---|
| VM added to / removed from `lv3_guests` | `make live-apply-service service=guest-log-shipping` | Loki log-agent topology derived from `lv3_guests`; new VMs produce no log streams until the agent is deployed |

Running `site.yml` (full-stack converge) satisfies all of the above automatically because
`playbooks/groups/observability.yml` imports all topology-tracking service playbooks.
For targeted VM-only runs (`make provision-guests`), apply each service in the table manually afterwards.

## Lessons Learned

- Proxmox guest network identity must be deterministic. Reapplying `qm set --net0 virtio,bridge=...` without an explicit MAC can assign a new MAC address, while Debian 13 cloud-init or systemd-networkd may still match the previous MAC in generated network config. The result is a guest that boots with no usable network even though the intended static config exists.
- For managed guests, pin the MAC address in repo config and keep it stable across reruns. Treat the MAC as part of the guest identity, not as disposable runtime state.
- After changing guest cloud-init inputs such as `net0`, `ipconfig0`, or `cicustom`, refresh the seed data with `qm cloudinit update <vmid>` before restarting the guest. Do not assume `qm set` alone is enough.
- On first boot or early bootstrap, prefer a Proxmox stop/start cycle over `qm reboot` when the guest agent may not be running yet. `qm reboot` can fail with a qga timeout even when the VM itself is otherwise healthy.
- NEVER create symlinks to `.local/` or any credential directory. A symlink named `.local` is not matched by a directory-only ignore pattern, and committing it destroys the real credential store when checked out; `.gitignore` lists both `.local/` and bare `.local`, and a pre-commit hook blocks any staged `.local` path. (See ADR 0376.)
- NEVER run `git add .local`, `git add -A`, or `git add .` in any directory containing `.local`. Always name specific files or directories when staging.
- Agents in worktrees do NOT have `.local/` — this is intentional. If credentials are needed, read from the main worktree path directly. Do not create symlinks, copies, or placeholder credentials.
- Never hand-maintain a security boundary list (like sanitization patterns) without an automated audit. The initial publication sanitization config missed 7 of 25 VMs (28% miss rate) and an IPv6 address in a template file. The drift detector (`make audit-sanitization`) catches these gaps automatically.
- NEVER manually edit `platform_service_registry.host_group`, `proxy.upstream_host`, or `platform_service_topology[svc].owning_vm` in isolation when migrating a service. All three must change together. Use `make migrate-service svc=X to=Y` — it updates the registry fields in one run (not transactionally) and then runs the converges in dependency order. Manual multi-step edits caused three drift incidents in 72 hours (ADR 0416 postmortem).
- If a service fails to connect to PostgreSQL after a VM migration, the cause is almost always a stale pg_hba.conf entry. Run `make converge-postgres-vm env=production` — since ADR 0416 Phase 2, pg_hba.conf derives client IPs from `platform_service_registry.host_group` automatically. You only need to ensure `host_group` is correct.
