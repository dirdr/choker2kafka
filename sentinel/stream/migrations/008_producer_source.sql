ALTER TABLE sentinel.producer_configurations ADD COLUMN source_commit TEXT;
ALTER TABLE sentinel.producer_configuration_history ADD COLUMN source_commit TEXT;
ALTER TABLE sentinel.producer_configuration_history ADD COLUMN source_file_sha TEXT;

CREATE TABLE sentinel.producer_sources (
    producer_id TEXT PRIMARY KEY REFERENCES sentinel.producer_configurations,
    repository TEXT,
    branch TEXT,
    file_path TEXT NOT NULL,
    file_sha TEXT NOT NULL,
    commit_sha TEXT,
    applied_revision BIGINT NOT NULL,
    configuration JSONB NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
