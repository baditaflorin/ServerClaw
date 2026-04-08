-- ADR 0118 — Replayable Failure Case Library
-- Migration: 0018_cases_schema.sql
--
-- Creates the cases schema and failure_cases table with full-text search,
-- trigram index, and all indexes required for service/category/status lookups.
-- Safe to run multiple times (all statements use IF NOT EXISTS).

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS cases;

CREATE TABLE IF NOT EXISTS cases.failure_cases (
    id                        BIGSERIAL PRIMARY KEY,
    case_id                   UUID        NOT NULL DEFAULT gen_random_uuid(),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    status                    TEXT        NOT NULL DEFAULT 'open',
    -- Allowed: open | resolved | archived
    title                     TEXT        NOT NULL,
    affected_service          TEXT        NOT NULL,
    -- Service identifier from the capability catalog (ADR 0092).
    symptoms                  TEXT[]      NOT NULL DEFAULT '{}',
    correlated_signals        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    root_cause                TEXT,
    root_cause_category       TEXT,
    -- Controlled vocabulary: config/case-root-cause-categories.yaml
    remediation_steps         TEXT[]      NOT NULL DEFAULT '{}',
    verification_command      TEXT,
    incident_duration_minutes INTEGER,
    first_observed_at         TIMESTAMPTZ,
    resolved_at               TIMESTAMPTZ,
    triage_report_id          UUID,
    -- Links to ADR 0114 triage ledger event.
    ledger_event_ids          UUID[]      NOT NULL DEFAULT '{}'::uuid[],
    -- All ADR 0115 ledger events for this incident.
    annotations               TEXT[]      NOT NULL DEFAULT '{}',
    search_vector             TSVECTOR    GENERATED ALWAYS AS (
        to_tsvector(
            'english',
            coalesce(title, '')                                    || ' ' ||
            coalesce(affected_service, '')                         || ' ' ||
            coalesce(root_cause, '')                               || ' ' ||
            coalesce(root_cause_category, '')                      || ' ' ||
            coalesce(array_to_string(symptoms, ' '), '')           || ' ' ||
            coalesce(array_to_string(remediation_steps, ' '), '')
        )
    ) STORED
);

-- Unique lookup by case UUID.
CREATE UNIQUE INDEX IF NOT EXISTS cases_failure_cases_case_id_idx
    ON cases.failure_cases (case_id);

-- Full-text search index (GIN on TSVECTOR).
CREATE INDEX IF NOT EXISTS cases_failure_cases_search_idx
    ON cases.failure_cases
    USING GIN (search_vector);

-- Service-scoped queries.
CREATE INDEX IF NOT EXISTS cases_failure_cases_service_idx
    ON cases.failure_cases (affected_service);

-- Category-scoped queries (used during triage hypothesis matching).
CREATE INDEX IF NOT EXISTS cases_failure_cases_category_idx
    ON cases.failure_cases (root_cause_category);

-- Status filter (open / resolved / archived).
CREATE INDEX IF NOT EXISTS cases_failure_cases_status_idx
    ON cases.failure_cases (status);

-- Chronological ordering of resolved cases.
CREATE INDEX IF NOT EXISTS cases_failure_cases_resolved_at_idx
    ON cases.failure_cases (resolved_at DESC NULLS LAST);

-- Trigram index for partial-title lookups in the ops portal.
CREATE INDEX IF NOT EXISTS cases_failure_cases_title_trgm_idx
    ON cases.failure_cases
    USING GIN (lower(title) gin_trgm_ops);
