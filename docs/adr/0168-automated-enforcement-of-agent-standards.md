# ADR 0168: Automated Enforcement of Agent Discovery and Handoff Standards

- Status: Proposed
- Implementation Status: Proposed
- Date: 2026-03-26

## Context

ADRs 0163-0167 introduce metadata standards and handoff protocols for LLM agents. However, **standards that rely on manual compliance will drift.**

Without automated enforcement:

- Playbooks will be created without metadata headers (ADR 0165)
- Agents will forget to update workstreams.yaml (ADR 0167)
- Commit messages won't follow the standard format (ADR 0167)
- Configuration changes won't have corresponding receipts
- `.config-locations.yaml` and ADR metadata indexes will become stale
- The next agent will spend time reconstructing context instead of reading documentation

Automated validation in the pre-push gate ensures standards are followed at commit time, making drift impossible and keeping documentation current.

## Decision

Add automated validation to the **pre-push-gate** (scripts/validate_repo.sh) that enforces:

### 1. Metadata Headers in Playbooks and Roles (ADR 0165)

**Validation Rule**: Every new or modified playbook/role must include metadata header.

```bash
# In scripts/validate_repo.sh

validate_playbook_metadata() {
  local playbooks=()
  local missing_metadata=()

  mapfile -t playbooks < <(
    git diff --name-only --cached |
    grep -E '^(playbooks|collections/.*roles)/.*\.ya?ml$'
  )

  for playbook in "${playbooks[@]}"; do
    # Check for metadata header (Purpose, Inputs, Outputs, Dependencies)
    if ! grep -q "^# Purpose:" "$playbook" 2>/dev/null; then
      missing_metadata+=("$playbook")
    fi
  done

  if [[ ${#missing_metadata[@]} -gt 0 ]]; then
    echo "ERROR: Playbooks/roles missing metadata headers (ADR 0165):"
    printf '  - %s\n' "${missing_metadata[@]}"
    echo "Add metadata header per: docs/adr/0165-playbook-role-metadata-standard.md"
    return 1
  fi
}
```

### 2. Workstreams.yaml Updated (ADR 0167)

**Validation Rule**: If changing files on a branch, must update workstreams.yaml.

```bash
validate_workstream_entry() {
  local current_branch
  local workstream_entry

  current_branch=$(git rev-parse --abbrev-ref HEAD)

  # Skip validation on main branch
  [[ "$current_branch" == "main" ]] && return 0

  # Check that branch appears in workstreams.yaml
  workstream_entry=$(grep -c "branch: \"$current_branch\"" workstreams.yaml 2>/dev/null || true)

  if [[ $workstream_entry -eq 0 ]]; then
    echo "ERROR: Branch '$current_branch' not found in workstreams.yaml (ADR 0167)"
    echo "Add entry: docs/adr/0167-agent-handoff-and-context-preservation.md#handoff-checklist"
    return 1
  fi
}
```

### 3. Commit Message Format (ADR 0167)

**Validation Rule**: Commits on branches must follow format: `[area] description` with Purpose/Scope/Status/Next sections.

```bash
validate_commit_format() {
  local current_branch
  local commit_msg
  local required_sections=("Purpose" "Scope" "Status")
  local section

  current_branch=$(git rev-parse --abbrev-ref HEAD)
  [[ "$current_branch" == "main" ]] && return 0  # Skip on main

  commit_msg=$(git log -1 --format=%B)

  # Check for required sections in commit message
  for section in "${required_sections[@]}"; do
    if ! echo "$commit_msg" | grep -q "^$section:"; then
      echo "ERROR: Commit message missing '$section:' section (ADR 0167)"
      echo "Required format:"
      echo "  [area] Short description"
      echo "  "
      echo "  Purpose: Why this matters"
      echo "  Scope: What changed"
      echo "  Status: Current implementation state"
      return 1
    fi
  done
}
```

### 4. Configuration Changes Have Receipts (ADR 0167)

**Validation Rule**: Changes to versions/stack.yaml or config/ must have a corresponding receipt.

```bash
validate_configuration_receipts() {
  local config_changes=()
  local recent_receipt

  mapfile -t config_changes < <(
    git diff --name-only HEAD~1 |
    grep -E '^(versions/stack\.yaml|config/)'
  )

  if [[ ${#config_changes[@]} -gt 0 ]]; then
    # Check for recent receipt file (modified in last 2 commits)
    recent_receipt=$(find receipts/ -name "*.yaml" -mtime -1 2>/dev/null | head -1)

    if [[ -z "$recent_receipt" ]]; then
      echo "WARNING: Configuration changes detected but no recent receipt found"
      echo "Create receipt: docs/adr/0167-agent-handoff-and-context-preservation.md#6-record-deployment-changes"
    fi
  fi
}
```

### 5. ADR Metadata Index is Current (ADR 0164)

**Validation Rule**: If docs/adr/ changed, must regenerate docs/adr/.index.yaml.

```bash
validate_adr_index_current() {
  local adr_changes
  local index_updated

  adr_changes=$(git diff --name-only --cached | grep '^docs/adr/0[0-9]' | wc -l)
  index_updated=$(git diff --name-only --cached | grep -c '^docs/adr/\.index\.yaml' || true)

  if [[ $adr_changes -gt 0 ]] && [[ $index_updated -eq 0 ]]; then
    echo "ERROR: ADR files changed but .index.yaml not updated (ADR 0164)"
    echo "Run: python scripts/generate_adr_index.py && git add docs/adr/.index.yaml"
    return 1
  fi
}
```

### 6. Configuration Locations Registry Updated (ADR 0166)

**Validation Rule**: If adding new config locations, must update .config-locations.yaml.

```bash
validate_config_registry_updated() {
  local new_config_files
  local registry_updated

  new_config_files=$(git diff --name-only --cached |
    grep -E '^(config/|inventory/|versions|docker)' | wc -l)
  registry_updated=$(git diff --name-only --cached |
    grep -c '^\.config-locations\.yaml' || true)

  if [[ $new_config_files -gt 3 ]] && [[ $registry_updated -eq 0 ]]; then
    echo "WARNING: New configuration files added but .config-locations.yaml not updated"
    echo "Consider documenting: .config-locations.yaml"
  fi
}
```

### 7. Repository Structure Index Updated (ADR 0163)

**Validation Rule**: If adding new directories or major reorganization, update .repo-structure.yaml.

```bash
validate_structure_index_updated() {
  local new_dirs
  local structure_updated

  new_dirs=$(git diff --name-only --cached |
    grep -o '^[^/]*/' | sort -u | wc -l)
  structure_updated=$(git diff --name-only --cached |
    grep -c '^\.repo-structure\.yaml' || true)

  if [[ $new_dirs -gt 1 ]] && [[ $structure_updated -eq 0 ]]; then
    echo "WARNING: New directories detected but .repo-structure.yaml not updated"
    echo "Consider updating: .repo-structure.yaml"
  fi
}
```

### Integration into pre-push-gate

Add to scripts/validate_repo.sh:

```bash
validate_agent_standards() {
  echo "Validating agent standards (ADR 0163-0167)..."

  validate_playbook_metadata || return 1
  validate_workstream_entry || return 1
  validate_commit_format || return 1
  validate_adr_index_current || return 1

  # Warnings (don't fail gate)
  validate_configuration_receipts || true
  validate_config_registry_updated || true
  validate_structure_index_updated || true
}
```

Add to `pre-push-gate` call in Makefile:

```makefile
pre-push-gate:
	$(REPO_ROOT)/scripts/remote_exec.sh pre-push-gate --local-fallback
	# After other validations:
	$(REPO_ROOT)/scripts/validate_repo.sh agent-standards
```

## Consequences

**Positive**

- Metadata standards are enforced at push time - no drift possible
- Agents must follow handoff protocol or push will fail
- Configuration changes automatically trigger reminders about receipts
- Documentation stays current because it's validated

**Negative / Trade-offs**

- Initial implementation requires Python scripts to generate indexes
- More validation adds 30-60 seconds to pre-push-gate
- Requires tooling maintenance to keep validators working

## Boundaries

- Validation is pre-push (before remote), enabling fast feedback
- Warnings don't block pushes, errors do
- Main branch bypasses most validations (different rules for stable code)
- Validation only applies to tracked files, not generated artifacts

## Implementation Tasks

1. [ ] Create `scripts/generate_adr_index.py` to generate `.index.yaml` from ADR files
2. [ ] Update `scripts/validate_repo.sh` with validation functions above
3. [ ] Add `agent-standards` to validate rule
4. [ ] Create git pre-commit hook to auto-fix simple issues (format trailing newlines, etc.)
5. [ ] Document how to bypass validation in `.githooks/pre-push` for emergency cases
6. [ ] Test validation against existing repo structure

## Related ADRs

- ADR 0163: Repository structure index
- ADR 0164: ADR metadata index
- ADR 0165: Playbook/role metadata standard
- ADR 0166: Configuration locations registry
- ADR 0167: Agent handoff and context preservation
- ADR 0031: Repository validation pipeline

## Automation Philosophy

> **Standards without enforcement are suggestions.**

This ADR operationalizes ADRs 0163-0167 by making compliance automatic and drift impossible. Agents don't need to remember the standards - the validation pipeline enforces them.
