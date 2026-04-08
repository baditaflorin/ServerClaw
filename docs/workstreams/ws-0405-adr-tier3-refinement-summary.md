# ADR Tier 3 Refinement Assessment — Workstream 0405

**Status**: Completed (First Pass - 20 ADRs analyzed)
**Date**: 2026-04-07
**Analysis Scope**: First 20 of 83 Tier 3 ADRs (high-priority subset)

---

## Executive Summary

This workstream addresses Tier 3 ADRs where the canonical implementation status ("Implemented") conflicts with the scanner's inferred status ("Possibly Implemented"). The first pass analyzed 20 high-priority ADRs using evidence depth methodology.

**Results**:
- **Upgraded to Partial Implemented**: 11 ADRs
- **Kept as Implemented**: 9 ADRs
- **Index Impact**:
  - Implemented: 317 → 306 (−11)
  - Partial: 16 → 27 (+11)

---

## Analysis Methodology

Each ADR underwent assessment across three dimensions:

### 1. Evidence Quantity
- **Single marker** (playbook ref, single commit): Weak→Partial
- **Two markers** (merge + record, multiple git refs): Implemented
- **3+ markers** (commits + playbooks + live-apply evidence): Implemented

### 2. Evidence Recency & Quality
- Recent commits (March 2026): Strong indicator of active implementation
- Live-apply records: Strongest evidence of actual production deployment
- Merge commits: Moderate evidence (architectural decision accepted)
- Playbook references: Moderate evidence (implementation framework identified)

### 3. Status Alignment
- **Accepted** status with evidence → Keep as-is (design decision confirmed)
- **Implemented** status with 1 marker → Upgrade to Partial (incomplete evidence)
- **Implemented** status with 3+ markers + playbook → Keep (strong evidence)

---

## Upgrade Decisions (Partial Implemented)

11 ADRs upgraded due to weak but valid evidence. All have at least one marker confirming implementation direction, but insufficient depth to claim "Implemented":

| ADR | Title | Markers | Evidence Type | Reasoning |
|-----|-------|---------|---------------|-----------|
| 0001 | Bootstrap Dedicated Host With Ansible | 1 | Playbook ref | Foundational bootstrap framework referenced in proxmox-install.yml; single marker justifies Partial |
| 0023 | Docker Runtime VM Baseline | 1 | Playbook ref | Referenced in docker-publication-assurance.yml; evidence is current |
| 0029 | Dedicated Backup VM With Local PBS | 1 | Merge commit | Merge explicitly recorded; partial automation evident |
| 0030 | Role Interface Contracts And Defaults Boundaries | 1 | Single commit | Pattern implemented but evidence is sparse |
| 0031 | Repository Validation Pipeline | 1 | Single commit | Validation patterns in place, single ref insufficient for "Implemented" claim |
| 0033 | Declarative Service Topology Catalog | 1 | Single commit | Topology framework referenced once; partial implementation confirmed |
| 0034 | Controller-Local Secret Manifest | 1 | Single commit | Secret handling patterns evident, requires deeper evidence for full claim |
| 0036 | Live Apply Receipts And Verification | 1 | Single commit | Receipt collection in place; single evidence marker means Partial |
| 0038 | Generated Status Documents | 1 | Single commit | Status generation implemented; single marker = Partial |
| 0044 | Windmill For Agent/Operator Workflows | 1 | Single commit | Workflow framework referenced; single marker insufficient |
| 0045 | Control-Plane Communication Lanes | 1 | Single commit | Communication patterns established; evidence is thin |

**Rationale**: Each has credible evidence (not speculation), but lacks the 2+ independent evidence types needed to claim "fully Implemented." Upgrading to "Partial Implemented" accurately reflects their status: architectural direction is sound and partially realized, but not comprehensively deployed across all subsystems.

---

## Keep as Implemented

9 ADRs retained at "Implemented" status due to strong evidence:

| ADR | Title | Markers | Evidence Type | Reasoning |
|-----|-------|---------|---------------|-----------|
| 0011 | Monitoring VM With Grafana | 2 | Merges | Foundational monitoring; two merge commits confirm adoption |
| 0028 | Docker Build Telemetry | 2 | Merge + Record | Build telemetry actively recorded; dual evidence |
| 0032 | Shared Guest Observability | 1 | Single ref | Status is "Accepted" (design decision), not "Implemented" re-classification needed |
| 0035 | Workflow Catalog | 2 | Multiple refs | Status is "Accepted"; 2 markers confirm direction |
| 0037 | Schema-Validated Data Models | 1 | Single ref | Status is "Accepted"; schema patterns foundational |
| 0039 | Shared Controller Toolkit | 2 | Git refs | Multiple implementation refs indicate solid adoption |
| 0040 | Docker Runtime Telemetry (Telegraf) | 4 | Merges + Playbook + Live-Apply | **Strongest evidence**: 4 markers + live-apply record (06f93a65c) = definitively Implemented |
| 0041 | Dockerized Mail Platform | 3 | Commits + Playbook + Live-Apply | **Very strong**: Email platform deployed in production; live-apply confirmed |
| 0043 | OpenBao Secrets Platform | 3 | Commits + Playbook + Live-Apply | **Very strong**: Secrets infrastructure live; multiple implementation refs |

**Rationale**:
- ADRs 0040, 0041, 0043: Unambiguous production evidence (live-apply records + multiple commit types + active playbooks). Retain "Implemented."
- ADRs 0032, 0035, 0037: "Accepted" status (design decisions), not re-classification candidates. Framework elements confirmed.
- ADRs 0011, 0028, 0039: 2+ evidence markers or foundational scope justify "Implemented" claim.

---

## Evidence Categories by Confidence

### High Confidence (3+ markers or live-apply)
- 0040 (4 markers, live-apply)
- 0041 (3 markers, live-apply)
- 0043 (3 markers, live-apply)

### Medium Confidence (2 markers)
- 0011 (merge + merge)
- 0028 (merge + record)
- 0035 (2 markers, Accepted status)
- 0039 (2 git refs)

### Lower Confidence (1 marker, upgraded to Partial)
- 0001, 0023, 0029, 0030, 0031, 0033, 0034, 0036, 0038, 0044, 0045

---

## Scanner Performance Notes

The scanner correctly identified implementation evidence in all 20 ADRs. The "Possibly Implemented" inference reflects the scanner's conservative threshold:

**Why scanner flags these as "Possibly"**:
- Single marker is insufficient (requires corroboration)
- Playbook references alone don't prove execution
- Commit messages mentioning an ADR ≠ proof of implementation

**This is appropriate conservatism**. Our manual review upgrades only when:
1. Evidence is credible (not speculation)
2. Pattern is consistent with ADR intent
3. Git history confirms recent work in this area

---

## Deferred ADRs (Remaining 63 from Tier 3)

These 63 ADRs await analysis in subsequent passes:
- 0046, 0047, 0049, 0050, 0052, 0054, 0055, 0056, 0057, 0059, 0060, 0062, 0064, 0065, 0066, 0067, 0069, 0070, 0072, 0074, 0075, 0076, 0077, 0080, 0081, 0082, 0083, 0084, 0085, 0086, 0087, 0088, 0089, 0090, 0091, 0092, 0093, 0094, 0095, 0096, 0097, 0098, 0099, 0101, 0102, 0103, 0104, 0105, 0106, 0107, 0109, 0110, 0111, 0112, 0113, 0114, 0115, 0116, 0117, 0119, 0120, 0121, 0122

**Recommendation**: Apply same methodology in Phase 8 with focus on:
- ADRs with 3+ markers (likely "keep Implemented")
- ADRs with live-apply evidence (definitely "keep Implemented")
- ADRs with only old commits (consider "downgrade to Accepted")

---

## Commit History Example: Evidence Pattern

For reference, the three strongest-evidence ADRs:

**ADR 0043 (OpenBao)**:
```
- a6336cffc docs: update ADRs 0043 and 0056 to reflect current topology (confidence 0.6)
- 87b57988c Implement ADR 0043 live with OpenBao (confidence 1.0, 2026-03-22)
- playbooks/openbao.yml reference (confidence 0.9)
```
Result: 3 markers × distinct types (docs, commit, playbook) + recent date → **Keep Implemented**

**ADR 0001 (Bootstrap)**:
```
- playbooks/proxmox-install.yml reference (confidence 0.9)
```
Result: 1 playbook reference, no corroborating commits → **Upgrade to Partial**

---

## Implementation Impact

**Index Updated**:
- docs/adr/.index.yaml (schema version 2)
- docs/adr/index/by-status/ (11 Partial files modified, 11 Implemented files modified)
- docs/adr/index/by-range/ (0000-0099 shard updated)

**ADR Files Modified**: 11 files updated with "Implementation Status: Partial Implemented"

**No Breaking Changes**: All updates are status clarifications. No ADRs downgraded from Implemented to Accepted in this pass.

---

## Next Steps

1. **Phase 8 (Remaining 63 ADRs)**: Apply same evidence-depth methodology
2. **Downgrade Reviews**: Identify ADRs with stale evidence (> 1 year, no follow-up commits)
3. **Category Analysis**: Group Partial ADRs by implementation area for prioritization
4. **Stakeholder Updates**: Brief teams on affected ADRs in their domains

---

## Glossary

- **Implemented**: Canonical status; code + evidence confirm full adoption
- **Partial Implemented**: Code patterns exist, but evidence is sparse or limited to one area
- **Accepted**: Design decision made; implementation may be in progress or deferred
- **Marker**: Detected evidence (playbook ref, git commit, etc.)
- **Confidence**: Scanner's confidence in evidence (0.6-1.0)
- **Live-Apply**: Production deployment evidence (highest confidence indicator)
