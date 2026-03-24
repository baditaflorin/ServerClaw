CREATE SCHEMA IF NOT EXISTS graph;

CREATE TABLE IF NOT EXISTS graph.nodes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    tier INTEGER,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS graph.edges (
    id BIGSERIAL PRIMARY KEY,
    from_node TEXT NOT NULL REFERENCES graph.nodes(id) ON DELETE CASCADE,
    to_node TEXT NOT NULL REFERENCES graph.nodes(id) ON DELETE CASCADE,
    edge_kind TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT graph_edges_unique UNIQUE (from_node, to_node, edge_kind)
);

CREATE INDEX IF NOT EXISTS graph_edges_from_idx ON graph.edges (from_node);
CREATE INDEX IF NOT EXISTS graph_edges_to_idx ON graph.edges (to_node);
