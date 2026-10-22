ALTER TABLE sentinel.incidents ADD COLUMN configuration_revision BIGINT CHECK (configuration_revision > 0);

UPDATE sentinel.incidents i
SET configuration_revision = (
    SELECT (event->>'config_revision')::BIGINT
    FROM sentinel.incident_snapshots s,
         jsonb_array_elements(s.body->'snapshot'->'events') event
    WHERE s.snapshot_id = i.snapshot_id
      AND i.signal->'evidence_ids' ? ('event:' || (event->>'event_id'))
    ORDER BY (event->>'ingested_at')::TIMESTAMPTZ DESC, event->>'event_id' DESC
    LIMIT 1
);

DROP INDEX sentinel.incidents_active_episode_idx;
CREATE UNIQUE INDEX incidents_active_episode_idx
ON sentinel.incidents (run_id, topic, producer_id, contract_id, rule_id, affected_fields, configuration_revision)
NULLS NOT DISTINCT WHERE status <> 'resolved';
