CREATE SCHEMA IF NOT EXISTS memory;

CREATE TABLE IF NOT EXISTS memory.entries (
    memory_id            TEXT PRIMARY KEY,
    scope_kind           TEXT NOT NULL,
    scope_id             TEXT NOT NULL,
    object_type          TEXT NOT NULL,
    title                TEXT NOT NULL,
    content              TEXT NOT NULL,
    provenance           TEXT NOT NULL,
    retention_class      TEXT NOT NULL,
    consent_boundary     TEXT NOT NULL,
    delegation_boundary  TEXT,
    source_uri           TEXT,
    metadata             JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_refreshed_at    TIMESTAMPTZ NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at           TIMESTAMPTZ,
    CONSTRAINT memory_entries_scope_kind_ck
        CHECK (scope_kind IN ('owner', 'workspace'))
);

CREATE INDEX IF NOT EXISTS memory_entries_scope_idx
    ON memory.entries (scope_kind, scope_id);

CREATE INDEX IF NOT EXISTS memory_entries_object_type_idx
    ON memory.entries (object_type);

CREATE INDEX IF NOT EXISTS memory_entries_refresh_idx
    ON memory.entries (last_refreshed_at DESC);

CREATE INDEX IF NOT EXISTS memory_entries_expiry_idx
    ON memory.entries (expires_at);

CREATE INDEX IF NOT EXISTS memory_entries_metadata_gin_idx
    ON memory.entries USING GIN (metadata);
