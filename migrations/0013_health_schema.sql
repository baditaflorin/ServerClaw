CREATE SCHEMA IF NOT EXISTS health;

CREATE TABLE IF NOT EXISTS health.composite (
    service_id TEXT PRIMARY KEY,
    composite_status TEXT NOT NULL,
    composite_score NUMERIC(4, 3) NOT NULL,
    safe_to_act BOOLEAN NOT NULL,
    signals JSONB NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    ttl_seconds INTEGER NOT NULL DEFAULT 120
);

CREATE INDEX IF NOT EXISTS health_composite_status_idx ON health.composite (composite_status);
CREATE INDEX IF NOT EXISTS health_composite_safe_idx ON health.composite (safe_to_act);
