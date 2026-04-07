# ADR Implementation Status Scanner

## Overview

The ADR Implementation Status Scanner is a comprehensive tool for detecting and documenting actual implementation evidence for Architecture Decision Records in the repository. It scans git history, codebase structure, and configuration files to identify implementation markers and compare them against the canonical status claims in the ADR index.

**Purpose**: Provide visibility into the gap between ADR status claims (as recorded in `docs/adr/.index.yaml`) and actual implementation evidence in the codebase, enabling operators and agents to:

- Verify that "Implemented" ADRs have corresponding code artifacts
- Discover incomplete implementations marked as "Complete"
- Track implementation progress for "Partial" or "Proposed" ADRs
- Support validation gates and release checklists
- Audit ADR-to-implementation traceability

## Design Principles

### 1. Multiple Evidence Sources

The scanner aggregates signals from multiple sources:

- **Git History** — Commits mentioning ADR numbers
- **Ansible Roles** — Role directories and metadata containing ADR references
- **Playbooks** — Playbook files with ADR comments or names
- **Docker Compose Files** — Service definitions and ADR documentation
- **Configuration Files** — Config files with ADR-related references

### 2. Confidence Scoring

Each marker includes a confidence score (0.0–1.0) reflecting how directly it maps to the ADR:

- **1.0** — Direct ADR reference in commit message or role name
- **0.9** — High-confidence reference (e.g., "ADR 0058" in metadata)
- **0.85** — Strong indication (e.g., Compose file with ADR comment)
- **0.8** — Moderate indication (e.g., Config file with ADR reference)
- **0.6** — Weak indication (e.g., bare ADR number without context)

### 3. Heuristic Status Inference

Based on detected markers, the scanner infers a status:

- **Likely Implemented** — 3+ high-confidence markers OR 5+ git commits + 2+ structural markers
- **Possibly Implemented** — 1+ high-confidence markers OR 3+ git commits
- **Partial Evidence** — 1+ markers detected but insufficient for strong conclusion
- **No Evidence** — No markers found

### 4. Mismatch Detection

Reports flag discrepancies between:

- `canonical_status` — What the index claims
- `inferred_implementation_status` — What the scanner detected
- `status_match` — Boolean indicating whether they align

## Scanner Architecture

### Data Models

```python
ADRMetadata
  - adr_number: str
  - title: str
  - status: str (Accepted, Proposed, Deprecated, etc.)
  - implementation_status: str (Implemented, Partial, Not Implemented, etc.)
  - implemented_on: str | None
  - concern: str | None

ImplementationMarker
  - marker_type: str (git-commit, ansible-role, playbook, compose-file, config-file)
  - adr_number: str
  - location: str (file path or git ref)
  - evidence: str (human description)
  - confidence: float (0.0–1.0)

ADRImplementationReport
  - adr_number: str
  - title: str
  - canonical_status: str
  - canonical_implementation_status: str
  - detected_markers: list[ImplementationMarker]
  - inferred_implementation_status: str
  - status_match: bool
```

### Scan Pipeline

1. **Load ADR Index** — Read `docs/adr/.index.yaml` and all index shards
2. **Git History Scan** — Search commit messages for ADR references
3. **Ansible Role Scan** — Check for role names and metadata containing ADR keywords
4. **Playbook Scan** — Search playbook files for ADR references
5. **Compose File Scan** — Check Docker Compose files for ADR documentation
6. **Config File Scan** — Search config directories for ADR mentions
7. **Infer Status** — Combine marker confidence scores into an inferred status
8. **Generate Reports** — Output YAML and/or markdown reports

## Usage

### Scan Specific ADRs

```bash
python scripts/adr_implementation_scanner.py \
  --adr-numbers 0024,0025,0058,0061,0214,0215,0216,0217,0218,0219 \
  --output docs/adr/implementation-status/ \
  --format both
```

### Scan All ADRs

```bash
python scripts/adr_implementation_scanner.py \
  --scan-all \
  --output docs/adr/implementation-status/ \
  --format both
```

### Output Formats

- `--format yaml` — Machine-readable YAML reports only
- `--format markdown` — Human-readable markdown only
- `--format both` — Both formats (default)

### Output Structure

```
docs/adr/implementation-status/
  ├── INDEX.md                   # This file
  ├── INDEX.yaml                 # Generated scan summary
  ├── adr-0024.yaml              # Machine-readable report
  ├── adr-0024.md                # Human-readable report
  ├── adr-0025.yaml
  ├── adr-0025.md
  └── ... (additional ADRs)
```

## Report Fields

### YAML Report Structure

```yaml
adr_number: '0024'
title: Docker Guest Security Baseline
canonical_status: Accepted
canonical_implementation_status: Implemented
detected_markers:
  - marker_type: git-commit
    adr_number: '0024'
    location: 'git:a1d1cccd0'
    evidence: 'feat: docker guest security baseline — ADR 0024'
    confidence: 1.0
    detected_on: '2026-04-06T12:34:56.789012'
  - marker_type: ansible-role
    adr_number: '0024'
    location: 'collections/ansible_collections/lv3/platform/roles/docker_runtime'
    evidence: 'Role contains ADR reference'
    confidence: 0.9
    detected_on: '2026-04-06T12:34:56.789012'
inferred_implementation_status: Likely Implemented
status_match: true
summary: |
  Canonical Status: Implemented
  Inferred Status: Likely Implemented
  Markers Found: 5
  Breakdown: git-commit=3, ansible-role=2
  Implemented On: 2026-03-22
```

### Markdown Report Structure

Human-readable markdown with:
- Summary table (canonical status, inferred status, match indicator)
- Grouped markers by type
- Location, evidence, and confidence for each marker
- Qualitative assessment narrative

## Known Limitations

1. **Pattern Matching** — The scanner uses regex patterns and is case-insensitive but may miss indirect references (e.g., "Event Bus" for ADR 0058 without explicit "ADR 0058" mention).

2. **Git History Truncation** — Scans full `git log --all` but only returns commit hashes and summaries, not full diffs. Some implementation details may not appear in commit messages.

3. **False Positives** — Bare ADR numbers (e.g., "0024" in a service version) may be misattributed. Confidence scoring helps mitigate this.

4. **Repository Scope** — Only scans files under `REPO_ROOT`. External repositories or out-of-band implementations are not detected.

5. **Time Sensitivity** — Results reflect the current state of the repository. Deleted files or removed markers are not detected.

## Interpretation Guide

### Status Match = True

- **Canonical: Implemented + Inferred: Likely Implemented** — Strong alignment; ADR is well-documented in code
- **Canonical: Partial + Inferred: Partial Evidence** — Good alignment; implementation is incomplete as expected
- **Canonical: Not Implemented + Inferred: No Evidence** — Correct; no implementation work has begun

### Status Match = False

- **Canonical: Implemented + Inferred: No Evidence** — Red flag; implementation may be undocumented or removed
- **Canonical: Not Implemented + Inferred: Likely Implemented** — Possible; may indicate implementation happening before decision was formalized
- **Canonical: Partial + Inferred: No Evidence** — Possible; implementation may have been reverted

## Example Reports

Sample reports are generated for ADRs 0024, 0025, 0058, 0061, 0214, 0215, 0216, 0217, 0218, 0219 during scanner initialization:

- `adr-0024.md` — Docker Guest Security Baseline
- `adr-0025.md` — Compose-Managed Runtime Stacks
- `adr-0058.md` — NATS JetStream for Internal Event Bus
- `adr-0061.md` — GlitchTip for Application Exceptions
- `adr-0214.md` — (and others as indexed)

## Integration with CI/CD

The scanner can be integrated into pre-push or release gates to:

1. Verify that merged ADRs have at least "Possible" implementation evidence
2. Flag "Implemented" ADRs with "No Evidence" status as warnings
3. Generate implementation traceability reports for release notes
4. Audit ADR-to-code links during public repository preparation

Example gate check:

```bash
# Fail if any "Implemented" ADR has "No Evidence"
python scripts/adr_implementation_scanner.py --scan-all --format yaml \
  --output /tmp/adr-status && \
python -c "
import yaml
with open('/tmp/adr-status/INDEX.yaml') as f:
  index = yaml.safe_load(f)
  if index['scan_summary']['no_evidence'] > 0:
    print('ERROR: ADRs marked Implemented have no implementation evidence')
    exit(1)
"
```

## Extending the Scanner

To add new marker detection types:

1. Create a `scan_<type>()` function following the existing patterns
2. Return a list of `ImplementationMarker` objects
3. Call it in `main()` before report generation
4. Update docstring with the new type

Example:

```python
def scan_terraform_modules(adr_number: str) -> list[ImplementationMarker]:
    """Detect Terraform modules with ADR-derived names."""
    markers: list[ImplementationMarker] = []
    # ... implementation ...
    return markers
```

## Version History

- **1.0** (2026-04-06) — Initial release; supports git history, Ansible roles, playbooks, Compose files, and config files

## References

- ADR Index: `docs/adr/.index.yaml`
- ADR Metadata Schema: ADR 0017 (ADR Lifecycle and Implementation Metadata)
- Scanner Source: `scripts/adr_implementation_scanner.py`
