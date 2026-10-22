CREATE TABLE sentinel.demo_resets (
    reset_id TEXT PRIMARY KEY,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    removed JSONB NOT NULL
);
CREATE TABLE sentinel.ingestion_boundaries (
    topic TEXT NOT NULL,
    partition INTEGER NOT NULL,
    minimum_offset BIGINT NOT NULL CHECK (minimum_offset >= 0),
    PRIMARY KEY (topic, partition)
);
CREATE FUNCTION sentinel.enforce_ingestion_boundary() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM sentinel.ingestion_boundaries b
        WHERE b.topic = NEW.topic AND b.partition = NEW.partition
          AND NEW.kafka_offset < b.minimum_offset
    ) THEN
        RETURN NULL;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER events_reset_boundary BEFORE INSERT ON sentinel.events
FOR EACH ROW EXECUTE FUNCTION sentinel.enforce_ingestion_boundary();
CREATE TRIGGER rejected_reset_boundary BEFORE INSERT ON sentinel.rejected_records
FOR EACH ROW EXECUTE FUNCTION sentinel.enforce_ingestion_boundary();
