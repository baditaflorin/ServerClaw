# ADR 0135: Developer Portal Sensitivity Classification

- Status: Proposed
- Implementation Status: Not Implemented
- Implemented In Repo Version: not yet
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The developer portal (ADR 0094) renders ADRs, runbooks, the service catalog, API reference, and operational reference tables from the repository into a browsable site at `docs.lv3.org`. Authentication is now required (ADR 0133), but all authenticated operators see all content.

The problem is that documentation sensitivity is not uniform:

- An ADR that describes the high-level decision to use Proxmox is low sensitivity.
- An ADR that documents the exact credential rotation schedule, which secret IDs exist in OpenBao, or the break-glass recovery procedure contains details an attacker could exploit.
- A runbook titled "Recover from compromised Keycloak admin account" contains step-by-step instructions that are operationally valuable to an operator and equally valuable to an attacker.
- The service capability catalog (ADR 0075) includes health probe URLs, internal API endpoint paths, and dependency relationships — all useful for lateral movement.

Additionally, the developer portal uses search (ADR 0121) which indexes all content. A search for "break glass" or "recovery token" on the portal could surface sensitive runbook content to any authenticated operator, including a less-trusted contractor account.

The platform needs a **sensitivity classification** for ADRs and runbooks that governs which portal audience can see the full content, which can see a summary only, and which content should not appear in the portal at all.

## Decision

We will implement a **sensitivity classification system** for all ADR and runbook documents, enforced at the portal renderer and search indexer levels.

### Sensitivity levels

```yaml
# In ADR/runbook frontmatter:
sensitivity: PUBLIC        # Safe to display to any authenticated operator; may be shared externally
sensitivity: INTERNAL      # Any authenticated operator; not for external sharing
sensitivity: RESTRICTED    # platform-admin Keycloak role required; sensitive operational details
sensitivity: CONFIDENTIAL  # Visible only in raw/admin view; never indexed in portal search
```

Default for documents without a sensitivity field: `INTERNAL`.

### Classification guidance

| Content type | Default classification | Rationale |
|---|---|---|
| High-level architecture decisions (ADRs 0001–0050) | `PUBLIC` | No secrets; describes technology choices only |
| Service deployment ADRs | `INTERNAL` | Contains internal service names and config patterns |
| Security baseline ADRs (this series) | `INTERNAL` | Security controls should not be enumerated publicly |
| Break-glass and recovery runbooks | `RESTRICTED` | Step-by-step access to highest-privilege recovery procedures |
| Secret rotation runbooks | `RESTRICTED` | Describes rotation schedule and vault paths |
| Compromise response runbooks | `CONFIDENTIAL` | Should not be browseable even by general operators |
| Service capability catalog | `INTERNAL` | Internal endpoint URLs and dependency maps |
| API reference (public endpoints only) | `PUBLIC` | Documents the intentionally public API surface |

### Portal rendering rules

| User role | PUBLIC | INTERNAL | RESTRICTED | CONFIDENTIAL |
|---|---|---|---|---|
| Any authenticated operator | Full text | Full text | Title + summary only; "Request access" link | Not shown |
| `platform-admin` | Full text | Full text | Full text | Full text |

The "Request access" flow for `RESTRICTED` content sends a Mattermost notification to the `#platform-admin` channel; the admin can promote the operator to the `platform-admin` role in Keycloak for the duration needed.

### Frontmatter enforcement

The repository validation pipeline (ADR 0031) enforces that:
1. Every ADR and runbook has a `sensitivity` field in its frontmatter.
2. ADRs classified as `RESTRICTED` or `CONFIDENTIAL` have a `justification` field explaining why.
3. `CONFIDENTIAL` documents do not appear in any automated status generation or cross-reference tools (ADR 0038).

```yaml
# Example ADR frontmatter
---
sensitivity: RESTRICTED
justification: Contains break-glass account credentials path and recovery token format
---
```

### Search indexing rules

| Sensitivity | What is indexed |
|---|---|
| `PUBLIC` | Full title + body |
| `INTERNAL` | Full title + body (operator search only) |
| `RESTRICTED` | Title only; body not indexed |
| `CONFIDENTIAL` | Not indexed at all |

The search fabric (ADR 0121) reads the sensitivity field at index time and applies these rules. A search by an `INTERNAL`-role operator for "recovery token" will not surface `RESTRICTED` runbook body content.

### Retroactive classification

All 132 existing ADRs and all runbooks must be classified. A Windmill workflow `classify-portal-documents` will:
1. Parse all ADR and runbook frontmatter.
2. For documents with no `sensitivity` field, assign `INTERNAL` as default and write it to the frontmatter.
3. Flag documents that mention `break-glass`, `recovery`, `compromise`, `credential`, `root password`, `token`, or `secret path` for human review at `RESTRICTED` level.
4. Output a classification report to Mattermost `#platform-admin` for operator review.

## Consequences

**Positive**

- Sensitive operational content (break-glass procedures, recovery runbooks, compromise response) is not readable by all operators by default. A compromised general operator account cannot enumerate the platform's most sensitive procedures.
- Public-classification ADRs can be shared with external colleagues without portal access, removing the need for a separate public documentation site.
- The classification system is forward-compatible: as new ADRs are written, the sensitivity field is mandatory, so the problem does not recur.

**Negative / Trade-offs**

- Retroactive classification of 132 ADRs is a significant one-time effort. The automated workflow flags candidates but human review is required, particularly for ADRs that contain embedded code snippets referencing internal paths.
- `RESTRICTED` content is hidden from general operators by default, which could frustrate an operator who legitimately needs the recovery runbook during an incident. The Keycloak role promotion path (Mattermost request → admin approval) adds latency in an emergency. Critical recovery procedures should also exist as printed copies in a secure offline location.

## Boundaries

- Sensitivity classification governs portal display and search indexing. It does not restrict access to the raw git repository or Postgres ledger.
- This classification system is for documentation. It does not govern the sensitivity of live credentials, which are managed by OpenBao (ADR 0043) and never stored in documentation.

## Related ADRs

- ADR 0031: Repository validation pipeline (sensitivity field enforcement)
- ADR 0038: Generated status documents (CONFIDENTIAL documents excluded)
- ADR 0056: Keycloak SSO (platform-admin role for RESTRICTED access)
- ADR 0075: Service capability catalog (default: INTERNAL)
- ADR 0094: Developer portal (portal that enforces classification)
- ADR 0121: Local search and indexing fabric (indexes per classification rules)
- ADR 0133: Portal authentication by default (access control; this ADR covers content classification)
