CREATE TABLE sentinel.investigations (
    investigation_id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES sentinel.incidents,
    snapshot_id UUID NOT NULL REFERENCES sentinel.incident_snapshots,
    kind TEXT NOT NULL CHECK (kind IN ('original', 'retry')),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    model_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    token_limit INTEGER NOT NULL CHECK (token_limit BETWEEN 4000 AND 100000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    duration_ms INTEGER,
    finding JSONB,
    usage JSONB,
    error_code TEXT,
    retryable BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX investigations_original_idx ON sentinel.investigations (incident_id) WHERE kind = 'original';
CREATE UNIQUE INDEX investigations_active_idx ON sentinel.investigations (incident_id) WHERE status IN ('queued', 'running');
CREATE INDEX investigations_queue_idx ON sentinel.investigations (created_at) WHERE status = 'queued';

CREATE TABLE sentinel.investigation_activity (
    activity_id UUID PRIMARY KEY,
    investigation_id UUID NOT NULL REFERENCES sentinel.investigations,
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('started', 'returned')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    body JSONB NOT NULL
);
CREATE INDEX investigation_activity_run_idx ON sentinel.investigation_activity (investigation_id, recorded_at);
CREATE TRIGGER investigation_activity_immutable BEFORE UPDATE OR DELETE ON sentinel.investigation_activity FOR EACH ROW EXECUTE FUNCTION sentinel.prevent_evidence_mutation();
