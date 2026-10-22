CREATE SCHEMA IF NOT EXISTS sentinel;

CREATE TABLE IF NOT EXISTS sentinel.producer_configurations (
    producer_id TEXT PRIMARY KEY,
    revision BIGINT NOT NULL CHECK (revision > 0),
    event_time_unit TEXT NOT NULL CHECK (event_time_unit IN ('milliseconds', 'seconds', 'microseconds')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS sentinel.producer_configuration_history (
    producer_id TEXT NOT NULL,
    revision BIGINT NOT NULL,
    event_time_unit TEXT NOT NULL,
    previous_unit TEXT,
    reason TEXT NOT NULL,
    actor TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (producer_id, revision)
);

CREATE TABLE IF NOT EXISTS sentinel.events (
    event_id UUID PRIMARY KEY,
    topic TEXT NOT NULL,
    partition INTEGER NOT NULL,
    kafka_offset BIGINT NOT NULL,
    producer_id TEXT NOT NULL,
    code_version TEXT NOT NULL,
    config_revision BIGINT NOT NULL,
    event_time BIGINT NOT NULL,
    kafka_timestamp_ms BIGINT,
    kafka_timestamp_type TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    UNIQUE (topic, partition, kafka_offset)
);

CREATE INDEX IF NOT EXISTS events_ingested_at_idx ON sentinel.events (ingested_at DESC);
CREATE INDEX IF NOT EXISTS events_producer_revision_idx ON sentinel.events (producer_id, config_revision, ingested_at DESC);

CREATE TABLE IF NOT EXISTS sentinel.rejected_records (
    topic TEXT NOT NULL,
    partition INTEGER NOT NULL,
    kafka_offset BIGINT NOT NULL,
    kafka_timestamp_ms BIGINT,
    kafka_timestamp_type TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    payload BYTEA,
    reason TEXT NOT NULL,
    PRIMARY KEY (topic, partition, kafka_offset)
);

INSERT INTO sentinel.producer_configurations (producer_id, revision, event_time_unit)
VALUES ('checkout', 1, 'milliseconds') ON CONFLICT DO NOTHING;

INSERT INTO sentinel.producer_configuration_history
    (producer_id, revision, event_time_unit, reason, actor)
SELECT producer_id, revision, event_time_unit, 'Initial producer configuration', 'system'
FROM sentinel.producer_configurations
ON CONFLICT DO NOTHING;
