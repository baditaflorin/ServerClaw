CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS search;

CREATE TABLE IF NOT EXISTS search.documents (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL,
    collection TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    url TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash TEXT NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(body, '')), 'B')
    ) STORED
);

CREATE UNIQUE INDEX IF NOT EXISTS search_documents_docid_idx
    ON search.documents (doc_id, collection);

CREATE INDEX IF NOT EXISTS search_documents_fts_idx
    ON search.documents USING GIN (search_vector);

CREATE INDEX IF NOT EXISTS search_documents_trgm_idx
    ON search.documents USING GIN (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS search_documents_collection_idx
    ON search.documents (collection);

CREATE INDEX IF NOT EXISTS search_documents_metadata_idx
    ON search.documents USING GIN (metadata);
