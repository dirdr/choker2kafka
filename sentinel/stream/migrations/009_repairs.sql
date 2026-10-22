ALTER TABLE sentinel.incidents ADD COLUMN resolved_at TIMESTAMPTZ;
CREATE TABLE sentinel.repairs (
    repair_id UUID PRIMARY KEY,
    incident_id UUID NOT NULL UNIQUE REFERENCES sentinel.incidents,
    investigation_id UUID NOT NULL REFERENCES sentinel.investigations,
    status TEXT NOT NULL CHECK (status IN ('queued', 'opening', 'open', 'merged', 'verified', 'stale', 'closed', 'blocked', 'error')),
    proposal JSONB NOT NULL,
    repository TEXT,
    base_branch TEXT,
    branch TEXT NOT NULL,
    pr_number INTEGER,
    pr_url TEXT,
    repair_file_sha TEXT,
    merge_commit TEXT,
    recovery_revision BIGINT,
    error_code TEXT,
    retry_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE sentinel.recovery_windows (
    repair_id UUID NOT NULL REFERENCES sentinel.repairs,
    configuration_revision BIGINT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    passed BOOLEAN NOT NULL,
    evidence JSONB NOT NULL,
    PRIMARY KEY (repair_id, window_end)
);
CREATE TRIGGER recovery_windows_immutable
BEFORE UPDATE OR DELETE ON sentinel.recovery_windows
FOR EACH ROW EXECUTE FUNCTION sentinel.prevent_evidence_mutation();
