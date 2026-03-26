CREATE TABLE IF NOT EXISTS config_change_staging (
    change_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path TEXT NOT NULL,
    operation TEXT NOT NULL,
    key_value TEXT NOT NULL,
    entry_json JSONB,
    submitted_by TEXT NOT NULL,
    context_id UUID NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    merged_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending',
    status_reason TEXT,
    CONSTRAINT config_change_staging_operation_chk
        CHECK (operation IN ('append', 'update', 'delete')),
    CONSTRAINT config_change_staging_status_chk
        CHECK (status IN ('pending', 'merged', 'conflict', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_config_change_staging_status_submitted
    ON config_change_staging (status, submitted_at);

CREATE INDEX IF NOT EXISTS idx_config_change_staging_file_status
    ON config_change_staging (file_path, status, submitted_at);
