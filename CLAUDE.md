# Claude Code — Session Protocol

This file is read automatically by Claude Code at session start.
It supplements `AGENTS.md` with Claude-specific checklists and context.

---

## 1. Session Start — Read These First

Before writing any code, in order:

1. `README.md` — current platform status and merged deployment truth
2. `AGENTS.md` — working rules, conventions, handoff protocol
3. `workstreams.yaml` — what is in flight, who owns which surfaces
4. `.repo-structure.yaml` — where everything lives (use instead of `find`)
5. Check Claude Code memory for any remembered context from prior sessions on this repo

If the task touches a specific service, also read:
- `docs/adr/.index.yaml` — search for the ADR covering that service
- The relevant workstream doc under `docs/workstreams/`

---

## 2. Before Starting Work — Open a Workstream

Every non-trivial task needs a workstream entry **before** writing code.
This is how other agents (and future-you) find what is in flight.

**Minimal steps:**
```
1. Pick or create a branch: claude/<worktree-name>
2. Create a worktree: git worktree add .claude/worktrees/<name> -b claude/<name>
3. Add an entry to workstreams/active/<id>.yaml (or ask the user if one already exists)
4. Regenerate workstreams.yaml: python3 scripts/workstream_registry.py --write
5. Commit the workstream registration before starting the real work
```

**Skip this only for** single-commit typo fixes or explicit user instruction.

---

## 3. Work Rules (summary of AGENTS.md)

- Decisions → `docs/adr/` (use `docs/adr/.index.yaml` to find the right ADR number)
- Procedures → `docs/runbooks/`
- Shared facts go in one place; never duplicate across roles/templates
- Do not hardcode IPs, domains, or paths that belong in inventory or `.local/`
- Do not touch `VERSION`, `changelog.md`, `versions/stack.yaml`, or `README.md`
  on a branch — only on `main` during the integration step
- Pre-push gate runs Docker validation on the build server (10.10.10.30);
  if unreachable it falls back locally — Docker must be installed locally or
  use `SKIP_REMOTE_GATE=1` with a `GATE_BYPASS_REASON_CODE`

---

## 4. Merge-to-Main Checklist

Run this **every time** work lands on `main`. Do not skip steps.

### 4a. Bump VERSION
```bash
# Read current version
cat VERSION   # e.g. 0.178.7

# Bump patch (or minor for breaking changes per config/version-semantics.json)
echo "0.178.8" > VERSION
```

### 4b. Add a changelog entry
Edit `changelog.md` — add a bullet under `## Unreleased`:
```markdown
## Unreleased

- <one-line summary of what merged>
```

### 4c. Write release notes
```bash
# The Unreleased section becomes the release notes body.
# Run after editing changelog.md:
uv run --with pyyaml \
  python scripts/generate_release_notes.py \
  --version 0.178.8 \
  --released-on $(date +%Y-%m-%d) \
  --write

# This creates docs/release-notes/0.178.8.md and updates RELEASE.md.
# Then refresh the index and changelog release sections:
uv run --with pyyaml \
  python scripts/generate_release_notes.py --write-root-summaries
```

### 4d. Regenerate platform manifest and discovery artifacts
```bash
uvx --python 3.12 \
  --with pyyaml --with jsonschema --with requests --with jinja2 \
  python scripts/platform_manifest.py --write

python scripts/generate_discovery_artifacts.py --write
```

### 4e. Commit everything together
```bash
git add VERSION changelog.md RELEASE.md docs/release-notes/ \
        build/platform-manifest.json build/onboarding/
git commit -m "[release] Bump to 0.178.8 — <one-line summary>"
```

### 4f. Push
```bash
git push origin main
```

---

## 5. Live-Apply Checklist

Run this **after** an Ansible playbook successfully deploys to production.

### 5a. Bump platform_version in versions/stack.yaml
```yaml
# Increment the patch:
platform_version: 0.130.99   # was 0.130.98
```

### 5b. Update the service receipt in versions/stack.yaml
```yaml
live_apply_evidence:
  latest_receipts:
    api_gateway: 2026-04-05-portainer-tools-live-apply   # descriptive slug
```

### 5c. Commit
```bash
git add versions/stack.yaml
git commit -m "[live-apply] <service> deployed — <brief description>"
git push origin main
```

---

## 6. Key Commands Reference

| Task | Command |
|------|---------|
| Run a playbook | `make converge-<service> env=production` (from repo root) |
| Before running any playbook | Rename `.local/open-webui/provider.env` and `.local/serverclaw/provider.env` to `.bak`; restore after. These files trip the preflight `.env` scanner. |
| Sync Dify tools | `python scripts/sync_tools_to_dify.py --base-url http://10.10.10.20:8094 ...` (internal URL — bypasses oauth2-proxy) |
| Bump platform manifest | `uvx --python 3.12 --with pyyaml --with jsonschema --with requests --with jinja2 python scripts/platform_manifest.py --write` |
| Regenerate discovery artifacts | `python scripts/generate_discovery_artifacts.py --write` |
| Regenerate workstreams.yaml | `python3 scripts/workstream_registry.py --write` |
| Generate release notes | `uv run --with pyyaml python scripts/generate_release_notes.py --version X.Y.Z --released-on YYYY-MM-DD --write` |
| Refresh changelog/index | `uv run --with pyyaml python scripts/generate_release_notes.py --write-root-summaries` |
| Skip remote gate (with reason) | `SKIP_REMOTE_GATE=1 GATE_BYPASS_REASON_CODE=<code> git push origin main` |
| Publish to ServerClaw (dry-run) | `make publish-serverclaw` |
| Publish to ServerClaw (push) | `make publish-serverclaw-push` |
| Audit sanitization coverage | `make audit-sanitization` |

---

## 7. Platform Topology Quick Reference

| Host | IP | Purpose |
|------|----|---------|
| Proxmox host | 10.10.10.1 | Hypervisor |
| runtime-control-lv3 | 10.10.10.92 | API gateway, agent tools, Docker runtime |
| postgres-vm-lv3 | 10.10.10.60 | Shared PostgreSQL |
| build server | 10.10.10.30 | Docker build + pre-push gate runner |
| Dify internal | 10.10.10.20:8094 | Dify API (bypasses oauth2-proxy) |

SSH to guests uses `proxmox_host_jump` connection mode via the bootstrap key at `.local/ssh/bootstrap.id_ed25519`.

---

## 8. Protected Integration Surfaces

These files must only change on `main` during an explicit integration step:

- `VERSION`
- `changelog.md` (the `## Unreleased` and `## Latest Release` sections)
- `RELEASE.md`
- `versions/stack.yaml`
- `README.md` (top-level status summaries)
- `workstreams.yaml` (generated — use `workstream_registry.py --write`)

Branch-local changes to these will be overwritten or conflict on merge.

---

## 9. Deployment-Specific Values (ADR 0407)

The committed codebase uses **generic values** (`example.com`, `Platform Operator`,
`203.0.113.x`). Real deployment values live exclusively in `.local/`:

| What | Committed (generic) | Real value location |
|------|---------------------|---------------------|
| Domain | `example.com` | `.local/identity.yml` → `platform_domain: lv3.org` |
| Operator | `Platform Operator` | `.local/identity.yml` → `platform_operator_name` |
| Email | `operator@example.com` | `.local/identity.yml` → `platform_operator_email` |
| Host IPs | Template placeholders | `.local/hosts.yml` (future) |

**When you need the actual deployment domain, IP, or operator identity:**
1. Read `.local/identity.yml` first — it has the real values
2. The committed `identity.yml` is a structural reference with example values
3. Ansible automatically loads `.local/identity.yml` as extra-vars (highest precedence)
4. **Never hardcode values from `.local/` into committed files**

---

## 10. Common Pitfalls

**Preflight `.env` scanner** — `roles/preflight` uses `ansible.builtin.find *.env` recursively. It excludes by basename, not path, so `.local/open-webui/provider.env` and `.local/serverclaw/provider.env` are always found. Temporarily rename them to `.bak` before any `make converge-*` run and restore after.

**Dify URL** — The Dify subdomain is behind oauth2-proxy. Use the internal Dify IP and port for API calls from the controller.

**Top-level imports in agent_tool_registry.py** — Any `import` that requires `requests` at module load time breaks `--export-mcp` validation (which runs in a container without `requests`). Always use lazy imports inside handler functions.

**Platform manifest must match committed code** — The pre-push gate validates `build/platform-manifest.json` against the current schema. Regenerate it after any structural change (new role, new tool, new playbook).

**Pre-push gate snapshot** — The gate validates a point-in-time snapshot of committed code. Fixes committed after a push attempt starts apply to the *next* push, not the current one.

**`.local/` is sacred** — NEVER symlink, copy, or `git add` the `.local` directory. Worktrees intentionally lack `.local/`; read credentials from the main worktree path if needed. Never generate placeholder secrets that could overwrite real ones. Never use `git add -A` or `git add .` in a directory containing `.local`. A pre-commit hook blocks `.local` from the index but defense in depth matters. See ADR 0376 for the full incident analysis.
