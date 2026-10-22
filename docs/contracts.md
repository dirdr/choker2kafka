# Contracts and detection

A contract declares expected data meaning. Producer configuration declares what the controlled producer currently does. Changing producer configuration never changes the contract.

The initial contract is authored in [orders.json](../sentinel/detection/fixtures/orders.json). Startup validates the definition and inserts its version into PostgreSQL. Existing versions are retained. A definition change must use a new version and a new `effective_from` timestamp; restarting does not overwrite a stored version. The fixture is adapted to `KAFKA_TOPIC` for the controlled checkout demo.

```json
{
  "contract_id": "orders.checkout",
  "version": 1,
  "topic": "orders",
  "owner": "checkout-team",
  "effective_from": "2026-01-01T00:00:00Z",
  "rules": [{
    "rule_id": "event-time-semantics",
    "kind": "timestamp_bounds",
    "fields": ["event_time"],
    "parameters": {
      "unit": "milliseconds",
      "max_age_seconds": 60,
      "max_future_seconds": 5
    }
  }]
}
```

Rule kinds select registered detector functions. Only `timestamp_bounds` is implemented. A future enum or null-ratio check needs its own pure detector, parameter validation, fixtures and tests. Existing signal, capture and incident storage can be reused. Unsupported kinds are reported explicitly.

For this slice, effective contract versions are selected using ingestion time. Business time is the field being checked and cannot reliably select its own policy when corrupted. The active version is recorded in each evaluation; a signal retains the version effective for the latest failing record. Captured snapshots include all contract versions needed by their event windows.

Every five seconds the worker evaluates adjacent windows `[evaluation - 70s, evaluation - 10s)` and `[evaluation - 10s, evaluation)`. It requires 100 baseline and 50 recent samples. A signal requires strictly more than 80% recent failures. Bounds are evaluated relative to each record's own ingestion time, without converting extreme business timestamps into datetime objects.

Profiles include sample counts, failure ratios, medians, median scale change and whether multiplying or dividing failed values by 1,000 restores plausibility. These are evidence, not a claim that a configuration change caused the violation. Delayed millisecond events can fail the contract without supporting a unit-change diagnosis.

Transport freshness includes rejected traffic. No arrivals for ten seconds produce `stale`; insufficient valid samples produce `warming_up`. Neither is healthy. A snapshot exceeding 2,000 events or 100 relevant contract versions produces `evidence_limit` instead of a partial diagnosis.

The first signal in an active episode atomically creates an incident, snapshot and timeline entry. The snapshot freezes event windows, Kafka provenance, profiles, effective contracts, available configuration history and versioned consumer context. Missing configuration revisions are listed explicitly. Consumer metadata is synthetic; memory retrieval is not implemented and is labelled accordingly in the capture.

Monitoring run identity survives process restarts. A uniqueness constraint suppresses repeat active incidents for the same run, producer, topic, rule and fields. Contract versions, context versions, snapshots and timeline entries reject updates/deletes through database triggers. A healthy check does not resolve an open incident: action authorization and verified recovery belong to the next slices.

## Live verification

1. Redeploy the latest application and allow about 70 seconds of healthy orders to establish a baseline.
2. Read `GET /api/contracts` and `GET /api/detection`; expect a millisecond contract and a healthy check.
3. Read `GET /api/producer/configuration`, then use its revision to patch `event_time_unit` to `seconds` with the operator bearer token.
4. Allow 15–20 seconds, then read `GET /api/incidents`. One open incident should appear.
5. Read `GET /api/incidents/{id}` for the signal/timeline and `GET /api/incidents/{id}/evidence` for the captured sources.
6. Restore milliseconds using the current producer revision. New checks should become healthy while the incident and its original evidence remain recorded.
7. Restart the application and verify it retains the same active incident and snapshot.

The read APIs do not publish events, create incidents or execute model calls. Capture happens automatically in the background worker. No new Runtime secret is needed; `DETECTION_ENABLED` defaults to `true` and can be set to `false` to stop that worker independently of ingestion.
