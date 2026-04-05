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

`tasks.lv3.org` is the **Agent Work HQ**. Every non-trivial agent session gets a
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

- **Git is authoritative.** Plane is a projection. If `tasks.lv3.org` is down,
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

## Nomad Scheduler (ADR 0232, ADR 0361)

The platform runs a private Nomad cluster for durable batch and long-running
internal jobs. Agents and operators can view, dispatch, and manage jobs.

| Resource | Location |
|---|---|
| **UI** | `https://scheduler.lv3.org` (OIDC login via Keycloak) |
| **API proxy** | `https://100.64.0.1:8013` (Tailscale, requires management token) |
| **Server** | `monitoring-lv3` (10.10.10.40:4646) |
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
