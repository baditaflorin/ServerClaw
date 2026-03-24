CREATE SCHEMA IF NOT EXISTS agent;

CREATE TABLE IF NOT EXISTS agent.state (
    state_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    context_id UUID,
    written_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT agent_state_key_nonempty CHECK (length(trim(key)) > 0),
    CONSTRAINT agent_state_agent_nonempty CHECK (length(trim(agent_id)) > 0),
    CONSTRAINT agent_state_task_nonempty CHECK (length(trim(task_id)) > 0),
    CONSTRAINT agent_state_version_positive CHECK (version > 0),
    CONSTRAINT agent_state_expiry_after_write CHECK (expires_at > written_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS agent_state_uq_idx
    ON agent.state (agent_id, task_id, key);

CREATE INDEX IF NOT EXISTS agent_state_expiry_idx
    ON agent.state (expires_at);

CREATE INDEX IF NOT EXISTS agent_state_task_idx
    ON agent.state (task_id, agent_id);

CREATE OR REPLACE FUNCTION agent.enforce_state_limits()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF octet_length(convert_to(NEW.value::text, 'UTF8')) > 65536 THEN
        RAISE EXCEPTION 'agent.state value exceeds 64 KB';
    END IF;

    IF (
        SELECT COUNT(*)
        FROM agent.state
        WHERE agent_id = NEW.agent_id
          AND task_id = NEW.task_id
          AND expires_at > now()
          AND (TG_OP = 'INSERT' OR key <> NEW.key)
    ) >= 100 THEN
        RAISE EXCEPTION 'agent.state namespace exceeds 100 active keys';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agent_state_limits ON agent.state;

CREATE TRIGGER agent_state_limits
BEFORE INSERT OR UPDATE ON agent.state
FOR EACH ROW
EXECUTE FUNCTION agent.enforce_state_limits();
