CREATE SCHEMA IF NOT EXISTS world_state;

CREATE TABLE IF NOT EXISTS world_state.surface_config (
    surface TEXT PRIMARY KEY,
    refresh_interval_seconds INTEGER NOT NULL CHECK (refresh_interval_seconds > 0),
    stale_threshold_seconds INTEGER NOT NULL CHECK (stale_threshold_seconds > 0),
    summary TEXT NOT NULL
);

INSERT INTO world_state.surface_config (surface, refresh_interval_seconds, stale_threshold_seconds, summary)
VALUES
    ('proxmox_vms', 60, 300, 'Proxmox VM inventory and runtime state'),
    ('service_health', 30, 120, 'Service health probe rollup'),
    ('container_inventory', 60, 300, 'Runtime container inventory'),
    ('netbox_topology', 300, 1800, 'NetBox topology snapshot'),
    ('dns_records', 300, 1800, 'Published DNS records'),
    ('tls_cert_expiry', 3600, 21600, 'TLS certificate expiry inventory'),
    ('opentofu_drift', 900, 3600, 'OpenTofu drift summary'),
    ('openbao_secret_expiry', 300, 1800, 'OpenBao lease and secret expiry'),
    ('maintenance_windows', 60, 300, 'Active maintenance windows')
ON CONFLICT (surface) DO UPDATE
SET
    refresh_interval_seconds = EXCLUDED.refresh_interval_seconds,
    stale_threshold_seconds = EXCLUDED.stale_threshold_seconds,
    summary = EXCLUDED.summary;

CREATE TABLE IF NOT EXISTS world_state.snapshots (
    id BIGSERIAL PRIMARY KEY,
    surface TEXT NOT NULL REFERENCES world_state.surface_config(surface),
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    data JSONB NOT NULL,
    stale BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_world_state_snapshots_surface_collected_at
    ON world_state.snapshots (surface, collected_at DESC, id DESC);

DROP MATERIALIZED VIEW IF EXISTS world_state.current_view;

CREATE MATERIALIZED VIEW world_state.current_view AS
WITH latest AS (
    SELECT DISTINCT ON (surface)
        id,
        surface,
        collected_at,
        data,
        stale
    FROM world_state.snapshots
    ORDER BY surface, collected_at DESC, id DESC
)
SELECT
    latest.surface,
    latest.data,
    latest.collected_at,
    latest.stale,
    (now() - latest.collected_at) > make_interval(secs => config.stale_threshold_seconds) AS is_expired
FROM latest
JOIN world_state.surface_config AS config
    ON config.surface = latest.surface
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_world_state_current_view_surface
    ON world_state.current_view (surface);
