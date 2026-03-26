CREATE SCHEMA IF NOT EXISTS platform;

CREATE TABLE IF NOT EXISTS platform.idempotency_records (
    idempotency_key  TEXT PRIMARY KEY,
    workflow_id      TEXT NOT NULL,
    actor_id         TEXT NOT NULL,
    actor_intent_id  TEXT,
    target_service_id TEXT NOT NULL DEFAULT '',
    submitted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ,
    status           TEXT NOT NULL DEFAULT 'in_flight',
    windmill_job_id  TEXT,
    result           JSONB,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
    expires_at       TIMESTAMPTZ NOT NULL,
    CONSTRAINT platform_idempotency_status_ck
        CHECK (status IN ('in_flight', 'completed', 'failed', 'aborted', 'budget_exceeded', 'rolled_back'))
);

CREATE INDEX IF NOT EXISTS platform_idempotency_records_intent_idx
    ON platform.idempotency_records (actor_intent_id);

CREATE INDEX IF NOT EXISTS platform_idempotency_records_in_flight_idx
    ON platform.idempotency_records (workflow_id, target_service_id)
    WHERE status = 'in_flight';

CREATE INDEX IF NOT EXISTS platform_idempotency_records_expiry_idx
    ON platform.idempotency_records (expires_at);
