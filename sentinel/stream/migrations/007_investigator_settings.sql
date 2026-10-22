CREATE TABLE sentinel.investigator_settings (
    singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK (singleton),
    revision BIGINT NOT NULL CHECK (revision > 0),
    model_id TEXT NOT NULL CHECK (model_id ~ '^claude-[a-zA-Z0-9-]{1,120}$'),
    token_limit INTEGER NOT NULL CHECK (token_limit BETWEEN 4000 AND 100000),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE sentinel.investigator_settings_history (
    revision BIGINT PRIMARY KEY,
    model_id TEXT NOT NULL,
    token_limit INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TRIGGER investigator_settings_history_immutable
BEFORE UPDATE OR DELETE ON sentinel.investigator_settings_history
FOR EACH ROW EXECUTE FUNCTION sentinel.prevent_evidence_mutation();
