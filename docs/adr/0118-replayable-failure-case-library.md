# ADR 0118: Replayable Failure Case Library

- Status: Proposed
- Implementation Status: Partial
- Implemented In Repo Version: detected
- Implemented In Platform Version: not yet
- Implemented On: not yet
- Date: 2026-03-24

## Context

The triage engine (ADR 0114) fires on every alert and produces a hypothesis set. Its hypothesis quality depends on the coverage and precision of its rule table. Rules are written by operators based on patterns they have seen.

There is a compounding opportunity that the rule table alone cannot capture: the full richness of a past incident — the exact sequence of signals, the diagnostic path taken, the false leads explored, the actual root cause, the remediation steps, and the verification that the fix worked. This narrative context is useful for future incidents but it currently lives nowhere except in chat history and in the operator's memory.

The failure case library captures this narrative context in a structured, retrievable format. Unlike the triage engine's rule table (which fires on current signals), the case library is queried after initial triage to find the closest historical match for operator guidance.

The key insight is that this does not require vector embeddings or a language model. Most failure modes on a platform this size fall into a small number of recurring patterns. Symbolic matching (exact service names, error message substrings) combined with BM25 full-text search over structured fields is sufficient to retrieve the most relevant cases.

## Decision

We will build a **replayable failure case library** stored in Postgres with a full-text search index, queryable via the platform API gateway and surfaced in Mattermost incident posts.

### Case schema

```sql
CREATE TABLE cases.failure_cases (
    id              BIGSERIAL PRIMARY KEY,
    case_id         UUID NOT NULL DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    status          TEXT NOT NULL DEFAULT 'open',       -- open | resolved | archived
    title           TEXT NOT NULL,
    affected_service TEXT NOT NULL,                     -- service ID from the capability catalog
    symptoms        TEXT[] NOT NULL,                    -- short descriptive strings
    correlated_signals JSONB NOT NULL DEFAULT '[]',     -- signal key-value pairs at incident time
    root_cause      TEXT,                               -- written by operator after resolution
    root_cause_category TEXT,                           -- deployment_regression | resource_exhaustion | ...
    remediation_steps TEXT[] NOT NULL DEFAULT '{}',     -- ordered list of steps taken
    verification_command TEXT,                          -- command to confirm fix; must exit 0
    incident_duration_minutes INTEGER,
    first_observed_at TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ,
    triage_report_id UUID,                              -- links to ledger event (ADR 0115)
    ledger_event_ids UUID[] NOT NULL DEFAULT '{}',      -- all ledger events for this incident
    search_vector   TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english',
            title || ' ' ||
            affected_service || ' ' ||
            coalesce(root_cause, '') || ' ' ||
            coalesce(root_cause_category, '') || ' ' ||
            array_to_string(symptoms, ' ') || ' ' ||
            array_to_string(remediation_steps, ' ')
        )
    ) STORED
);

CREATE INDEX cases_search_idx ON cases.failure_cases USING GIN (search_vector);
CREATE INDEX cases_service_idx ON cases.failure_cases (affected_service);
CREATE INDEX cases_category_idx ON cases.failure_cases (root_cause_category);
CREATE INDEX cases_status_idx ON cases.failure_cases (status);
```

### Case lifecycle

Cases are created in two ways:

1. **Automatic creation**: when the triage engine (ADR 0114) fires and GlitchTip (ADR 0061) opens an incident, a Windmill workflow creates a skeleton case with `status: open`, populating `affected_service`, `correlated_signals`, and `triage_report_id` automatically.

2. **Operator creation**: the operator can create a case manually via `lv3 cases create` or the ops portal (ADR 0093) when an incident is discovered outside the automated triage path.

Cases are closed by the operator after resolution. Closing a case requires:
- `root_cause` text (one or two sentences)
- `root_cause_category` selected from the controlled vocabulary
- at least one `remediation_step`
- `verification_command` (optional but strongly encouraged)

### Retrieval

New incident triage queries the case library using a combination of:

1. **Exact service match**: filter by `affected_service = current_service`.
2. **Category match**: filter by `root_cause_category IN (top_triage_hypotheses)`.
3. **Full-text relevance**: rank surviving cases by BM25 relevance against the current incident's symptom strings and log error messages.
4. **Signal overlap score**: compute cosine similarity (using only integer/boolean signals — no embeddings) between the current `correlated_signals` and each case's `correlated_signals`.

The top 3 matching cases are appended to the triage report (ADR 0114) under a `similar_cases` key.

### Replay

Every case links to its full ledger event trail via `ledger_event_ids`. The replay API (ADR 0115) can reconstruct the exact platform state at the time of the incident:

```bash
lv3 cases replay <case-id>
# Outputs: timeline of events, before/after states for each mutation, final resolution
```

This replay is used for post-incident review and for validating that a recurring failure is the same root cause rather than a new variant.

### Controlled vocabulary for root_cause_category

```yaml
# config/case-root-cause-categories.yaml
- deployment_regression       # a deployment introduced the failure
- resource_exhaustion         # CPU, memory, disk, or connection pool saturation
- certificate_expiry          # TLS certificate expired or near-expired
- configuration_drift         # live config diverged from repo state
- dependency_failure          # upstream service failed first
- network_partition           # connectivity loss between components
- data_corruption             # database or file state corruption
- operator_error              # manual action caused the failure
- external_dependency         # failure in a service outside the platform
- unknown                     # root cause could not be determined
```

### Case quality enforcement

A weekly Windmill workflow audits case quality:
- Cases with `status: resolved` but missing `root_cause` are flagged and posted to Mattermost for operator attention.
- Cases with `verification_command` set are re-executed against the live platform; failures indicate the fix may have regressed.
- Cases older than 90 days in `status: open` are automatically moved to `status: archived` with an annotation.

## Consequences

**Positive**

- Platform operational memory compounds: every resolved incident becomes a retrievable asset for the next similar incident.
- The `similar_cases` output in triage reports reduces the time from alert to diagnosis because the operator sees "this looks like the deployment regression we had in March" rather than starting from scratch.
- The replay capability makes post-incident review precise: the exact sequence of platform mutations is recoverable without relying on chat history.
- No embedding pipeline or GPU infrastructure required; BM25 + signal overlap scoring is sufficient and inspectable.

**Negative / Trade-offs**

- Case quality depends entirely on operators filling in `root_cause` and `remediation_steps` after resolution. If operators close cases lazily, the library becomes a garbage-in, garbage-out system.
- Retrieval quality degrades for genuinely novel failures that share no symptoms with past cases. In those situations the library correctly returns no matches rather than a misleading false positive.
- The signal overlap scoring assumes signals are comparable across incidents; signals that changed meaning over time (e.g., a metric was renamed) will produce misleading similarity scores.

## Boundaries

- The case library stores operational knowledge about the platform's failure modes. It does not store customer data, PII, or secrets.
- Retrieval is symbolic and lexical. There is no embedding pipeline, no vector database, and no LLM in the retrieval path.
- The case library is advisory during triage. The triage engine's hypothesis ranking is independent of the case library; cases are surfaced as supplementary context, not as the primary diagnosis.

## Related ADRs

- ADR 0057: Mattermost ChatOps (incident notification and case creation prompt)
- ADR 0061: GlitchTip failure signals (incident open event triggers case creation)
- ADR 0092: Unified platform API gateway (case CRUD and search API)
- ADR 0093: Interactive ops portal (case management UI)
- ADR 0098: Postgres HA (underlying storage)
- ADR 0114: Rule-based incident triage engine (triage reports linked to cases; similar cases returned in triage output)
- ADR 0115: Event-sourced mutation ledger (case event trail; replay capability)
- ADR 0121: Local search and indexing fabric (case library indexed here alongside ADRs and runbooks)
