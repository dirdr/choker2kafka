CREATE TABLE sentinel.contract_versions (
    contract_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    topic TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    definition JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (contract_id, version),
    UNIQUE (contract_id, effective_from)
);
CREATE INDEX contract_versions_topic_idx ON sentinel.contract_versions (topic, effective_from);

CREATE TABLE sentinel.producer_context_versions (
    producer_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    effective_from TIMESTAMPTZ NOT NULL,
    definition JSONB NOT NULL,
    PRIMARY KEY (producer_id, version),
    UNIQUE (producer_id, effective_from)
);

CREATE TABLE sentinel.monitoring_runs (
    run_id UUID PRIMARY KEY,
    topic TEXT NOT NULL,
    producer_id TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    ended_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX monitoring_runs_active_idx ON sentinel.monitoring_runs (topic, producer_id) WHERE ended_at IS NULL;

CREATE TABLE sentinel.contract_evaluations (
    evaluation_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES sentinel.monitoring_runs,
    topic TEXT NOT NULL,
    producer_id TEXT NOT NULL,
    contract_id TEXT NOT NULL,
    contract_version INTEGER NOT NULL,
    rule_id TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    result JSONB NOT NULL,
    FOREIGN KEY (contract_id, contract_version) REFERENCES sentinel.contract_versions,
    UNIQUE (run_id, contract_id, rule_id, evaluated_at)
);
CREATE INDEX contract_evaluations_latest_idx ON sentinel.contract_evaluations (topic, producer_id, evaluated_at DESC);

CREATE TABLE sentinel.incident_snapshots (
    snapshot_id UUID PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL,
    body JSONB NOT NULL
);

CREATE TABLE sentinel.incidents (
    incident_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES sentinel.monitoring_runs,
    topic TEXT NOT NULL,
    producer_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    affected_fields TEXT[] NOT NULL,
    contract_id TEXT NOT NULL,
    contract_version INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    opened_at TIMESTAMPTZ NOT NULL,
    snapshot_id UUID NOT NULL UNIQUE REFERENCES sentinel.incident_snapshots,
    signal JSONB NOT NULL,
    FOREIGN KEY (contract_id, contract_version) REFERENCES sentinel.contract_versions
);
CREATE UNIQUE INDEX incidents_active_episode_idx ON sentinel.incidents (run_id, topic, producer_id, contract_id, rule_id, affected_fields) WHERE status <> 'resolved';
CREATE INDEX incidents_opened_idx ON sentinel.incidents (opened_at DESC);

CREATE TABLE sentinel.incident_timeline (
    entry_id UUID PRIMARY KEY,
    incident_id UUID NOT NULL REFERENCES sentinel.incidents,
    kind TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    body JSONB NOT NULL
);
CREATE INDEX incident_timeline_incident_idx ON sentinel.incident_timeline (incident_id, recorded_at);
CREATE INDEX events_detection_window_idx ON sentinel.events (topic, producer_id, ingested_at DESC);
CREATE INDEX rejected_records_ingested_idx ON sentinel.rejected_records (topic, ingested_at DESC);

CREATE FUNCTION sentinel.prevent_evidence_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Evidence and source versions are append-only';
END;
$$;

CREATE TRIGGER contract_versions_immutable BEFORE UPDATE OR DELETE ON sentinel.contract_versions FOR EACH ROW EXECUTE FUNCTION sentinel.prevent_evidence_mutation();
CREATE TRIGGER producer_context_versions_immutable BEFORE UPDATE OR DELETE ON sentinel.producer_context_versions FOR EACH ROW EXECUTE FUNCTION sentinel.prevent_evidence_mutation();
CREATE TRIGGER incident_snapshots_immutable BEFORE UPDATE OR DELETE ON sentinel.incident_snapshots FOR EACH ROW EXECUTE FUNCTION sentinel.prevent_evidence_mutation();
CREATE TRIGGER incident_timeline_immutable BEFORE UPDATE OR DELETE ON sentinel.incident_timeline FOR EACH ROW EXECUTE FUNCTION sentinel.prevent_evidence_mutation();
