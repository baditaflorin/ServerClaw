CREATE SCHEMA IF NOT EXISTS handoff;

CREATE TABLE IF NOT EXISTS handoff.transfers (
    handoff_id UUID PRIMARY KEY,
    from_agent TEXT NOT NULL,
    to_agent TEXT NOT NULL,
    task_id TEXT NOT NULL,
    context_id UUID,
    handoff_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL,
    requires_accept BOOLEAN NOT NULL,
    timeout_seconds INTEGER NOT NULL,
    fallback TEXT NOT NULL,
    reply_subject TEXT,
    max_retries INTEGER NOT NULL DEFAULT 0,
    backoff_seconds INTEGER NOT NULL DEFAULT 5,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    response_decision TEXT,
    response_reason TEXT,
    estimated_completion_seconds INTEGER
);

CREATE INDEX IF NOT EXISTS handoff_transfers_to_idx ON handoff.transfers (to_agent, status);
CREATE INDEX IF NOT EXISTS handoff_transfers_task_idx ON handoff.transfers (task_id);
