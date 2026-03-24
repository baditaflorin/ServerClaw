CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS ledger;

CREATE TABLE IF NOT EXISTS ledger.events (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor TEXT NOT NULL,
    actor_intent_id UUID,
    tool_id TEXT,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    before_state JSONB,
    after_state JSONB,
    receipt JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ledger_events_event_id_unique UNIQUE (event_id)
);

CREATE INDEX IF NOT EXISTS ledger_events_occurred_at_idx ON ledger.events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ledger_events_target_idx ON ledger.events (target_kind, target_id);
CREATE INDEX IF NOT EXISTS ledger_events_actor_intent_idx
    ON ledger.events (actor_intent_id)
    WHERE actor_intent_id IS NOT NULL;

CREATE OR REPLACE FUNCTION ledger.prevent_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'ledger.events is append-only';
END;
$$;

DROP TRIGGER IF EXISTS ledger_events_append_only ON ledger.events;

CREATE TRIGGER ledger_events_append_only
BEFORE UPDATE OR DELETE ON ledger.events
FOR EACH ROW
EXECUTE FUNCTION ledger.prevent_event_mutation();
