# Contributing to ServerClaw Platform

Welcome! This document outlines the contribution guidelines and development practices for the ServerClaw Platform project.

## Code Organization

See `.repo-structure.yaml` for the repository structure and file locations.

## ADR (Architecture Decision Record) Governance

### Overview

All architecture decisions are recorded as ADRs in `docs/adr/`. The project enforces governance rules on ADR status changes to maintain accuracy and prevent regression.

**Three governance mechanisms are in place:**

1. **Pre-commit Hook Validation** — Local enforcement on every push
2. **Plane Integration** — Team visibility dashboard
3. **Quarterly Audit** — Automated drift detection

### ADR Status Fields

Each ADR has two status fields:

- **Status** (Decision Status): Accepted, Rejected, Superseded
  - **Rarely changes** — represents the architecture decision itself
  - Examples: "Accepted" (decided), "Superseded by ADR XXXX" (replaced)

- **Implementation Status** (What Actually Exists): Accepted, Partial, Partial Implemented, Implemented
  - **Changes frequently** — tracks whether the decision has been implemented
  - Examples: "Partial" (partially deployed), "Implemented" (fully in production)

### Rules for Changing ADR Implementation Status

#### ✅ Upgrading Status (e.g., Partial → Implemented)

**Requirement:** Evidence of implementation

**What counts as evidence:**
- **1+ git commit** mentioning the ADR in the last 180 days
  - Examples: "ADR-0025", "adr-0025", "[ADR 0025]"
- **1+ code reference** in roles, playbooks, compose files, or scripts
  - Examples: "adr_0025_enabled: true", "# ADR 0025: Compose stacks"

**Examples that will PASS pre-commit validation:**
```bash
# ✅ Recent commit mentioning ADR
git log --grep="ADR-0025" --since="6 months ago"  # Found commits → PASS

# ✅ Code reference in roles
grep -r "adr-0025" collections/ansible_collections/  # Found reference → PASS
```

**Examples that will FAIL pre-commit validation:**
```bash
# ❌ No evidence: no commits, no code references
# Pre-commit validation output:
# ERROR: ADR 0025: Cannot upgrade status from Partial to Implemented.
# No evidence found (0 commits, 0 code references).
# Evidence needed: 1+ git commit mentioning the ADR OR 1+ code reference.
```

#### ❌ Downgrading Status (e.g., Implemented → Partial)

**Requirement:** Explicit reason in commit message

**Commit message format:**
```
ADR-STATUS-CHANGE-REASON: <reason>
```

**Valid reasons:**
- "no evidence found" — implementation evidence disappeared
- "superseded by ADR XXXX" — replaced by newer ADR
- "design-only, never implemented" — designed but never actually deployed

**Example that will PASS:**
```bash
git commit -m "ADR 0025 status downgrade

ADR-STATUS-CHANGE-REASON: no evidence found"
```

**Example that will FAIL:**
```bash
git commit -m "Downgrade ADR 0025"
# ❌ Missing ADR-STATUS-CHANGE-REASON
# Pre-commit output:
# ERROR: ADR 0025: Cannot downgrade status without reason.
# Add to commit message: ADR-STATUS-CHANGE-REASON: <reason>
```

#### ↔️ Same-Tier Changes (e.g., Accepted ↔ Accepted)

**Always allowed** — no validation needed

### Bypassing Pre-commit Validation

If you need to bypass ADR validation (rare case):

```bash
SKIP_ADR_VALIDATION=1 GATE_BYPASS_REASON_CODE=build_server_unreachable \
  GATE_BYPASS_SUBSTITUTE_EVIDENCE="Your reason here" \
  GATE_BYPASS_REMEDIATION_REF="Link to issue or doc" \
  git push origin <branch>
```

This logs a bypass receipt in `receipts/gate-bypasses/` for audit trail.

### Provisioning ADR Governance Infrastructure (IaC)

The Plane project and API credentials are created programmatically through Infrastructure as Code:

#### Automated Provisioning (Recommended)

```bash
# Prerequisites: Get Plane admin token from workspace settings
# (Plane UI → Settings → API Tokens → Create Token)

# Test provisioning (dry-run)
make provision-adr-governance-dry-run PLANE_ADMIN_TOKEN=your_admin_token

# Execute provisioning
make provision-adr-governance PLANE_ADMIN_TOKEN=your_admin_token
```

**What happens:**
1. Ansible playbook runs on runtime_control_lv3
2. Creates Plane project "Architecture Decisions" (adr-index)
3. Generates API token for ADR sync
4. Saves credentials to `/root/.local/plane.env`
5. Displays next steps

#### Manual Provisioning (Development)

```bash
# Run provisioning script directly
python3 scripts/provision_plane_adr_project.py \
  --plane-url http://10.10.10.20:8093/api/v1 \
  --workspace-slug default \
  --admin-token YOUR_TOKEN \
  --output-file .local/plane.env
```

### Viewing ADR Status in Plane

All 406 ADRs are synced to Plane project `adr-index`:

```bash
# After provisioning, source the credentials
source /root/.local/plane.env  # On deployment host
source .local/plane.env         # On dev machine

# Test sync (dry-run)
make sync-adrs-to-plane-dry-run

# Execute sync
make sync-adrs-to-plane
```

**Plane Status Mapping:**
- Accepted → Backlog
- Partial → In Progress
- Implemented → Done

**IaC Files:**
- Playbook: `playbooks/provision_adr_governance.yml`
- Role: `collections/ansible_collections/lv3/platform/roles/plane_adr_provisioner/`
- Script: `scripts/provision_plane_adr_project.py`

### Quarterly Audit

Every first Monday of the quarter, an automated audit runs to detect drift:

```bash
# Test audit (dry-run)
make run-adr-quarterly-audit-dry-run

# Audit generates report with:
# - High confidence ADRs (5+ evidence markers)
# - Medium confidence (2-4 markers)
# - Low confidence (1 marker)
# - No evidence candidates (0 markers)
```

---

## Development Workflow

### Before Starting Work

1. **Check `workstreams.yaml`** — See what's in flight
2. **Read relevant ADRs** — Understand architecture decisions
3. **Use existing patterns** — Reference `AGENTS.md` for conventions

### Making Changes

1. **Create a branch** — `git checkout -b feature/your-feature`
2. **Make commits** — Small, focused changes
3. **Test locally** — Ensure pre-commit hooks pass
4. **Push to origin** — `git push origin feature/your-feature`

### ADR Changes During Development

If your work affects an ADR's implementation status:

1. **Gather evidence** — Commits, code patterns, documentation
2. **Update ADR frontmatter** — Change Implementation Status field
3. **Write commit message** — Reference the ADR and evidence
4. **Push** — Pre-commit hook validates transition

**Example commit:**
```bash
git add docs/adr/0025-compose-managed-runtime-stacks.md
git commit -m "ADR 0025: Upgrade to Implemented

Deployed compose-managed runtime stacks to docker-runtime-lv3.
Multiple recent commits (ab755354d, dcc9aa4fa, d718979ec) implement
the decision. Code references in keycloak_runtime, nginx_edge_publication roles."
```

---

## Protected Surfaces

These files only change on `main` during integration:

- `VERSION` — Semantic version (e.g., 0.178.52)
- `changelog.md` — Release notes (Unreleased and Latest Release sections)
- `RELEASE.md` — Root release summary
- `versions/stack.yaml` — Platform version state
- `README.md` — Top-level status
- `workstreams.yaml` — Generated from workstream files

Do not modify these on feature branches — they're updated during merge-to-main integration.

---

## Merge to Main Checklist

When your work is ready to merge to main:

1. **Bump VERSION** — Increment patch version
2. **Update changelog.md** — Add entry under "Unreleased"
3. **Generate release notes** — Run `python scripts/generate_release_notes.py --write`
4. **Regenerate artifacts** — Platform manifest and discovery documents
5. **Create final commit** — Includes all of above
6. **Push to main** — Pre-push gate validates

See `CLAUDE.md` section 4 for detailed integration checklist.

---

## Testing

### Pre-commit Hooks

Test that hooks work correctly:

```bash
# Test ADR validation
make validate-adr-transitions

# Test NATS topics validation
make validate-nats

# Test certificate validation
make validate-ssl-certificates
```

### Plane Sync

```bash
# Dry-run (no Plane API needed)
make sync-adrs-to-plane-dry-run

# With credentials (requires .local/plane.env)
source .local/plane.env
make sync-adrs-to-plane
```

### Quarterly Audit

```bash
# Dry-run (no Plane API needed)
make run-adr-quarterly-audit-dry-run

# Full audit (if first Monday of quarter)
make run-adr-quarterly-audit
```

---

## Getting Help

- **Architecture questions?** — See `docs/adr/.index.yaml` for ADR catalog
- **Convention questions?** — See `AGENTS.md` for working rules
- **ADR governance questions?** — See `docs/workstreams/ws-0408-adr-governance-implementation.md`
- **Repository structure?** — See `.repo-structure.yaml`

---

## Code Review Checklist

When reviewing PRs:

- [ ] **ADR changes valid?** — Check pre-commit hook passed (status transitions have evidence)
- [ ] **Architecture aligned?** — ADRs documenting the design?
- [ ] **Changelog updated?** — Unreleased section has entry?
- [ ] **Tests passing?** — Local and build server validation?
- [ ] **No protected files modified?** — VERSION, changelog, release notes should only change during integration?
- [ ] **Documentation clear?** — Changes documented in ADRs or runbooks?

---

## Questions or Issues?

Open an issue in the repository with:

1. **What you're trying to do** — Feature? Bug fix? ADR change?
2. **What happened** — Error message? Validation failure?
3. **What you expected** — What should have happened instead?

---

**Last Updated:** April 7, 2026
**ADR Governance Version:** 0.178.52
