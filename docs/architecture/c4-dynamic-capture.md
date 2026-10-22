# Event ingestion and automatic incident capture

This sequence separates the ingestion transaction from the later evaluation/capture transaction. Kafka and PostgreSQL do not share a distributed transaction.

```mermaid
sequenceDiagram
    title Sentinel event and incident recording
    participant Producer as Configured producer
    participant Kafka as Kafka orders topic
    participant Ingest as Ingestion worker
    participant PG as PostgreSQL
    participant Monitor as Detection worker
    participant Rule as Pure rule detector
    participant API as HTTP API
    participant Engineer as Platform engineer

    Producer->>PG: Read committed configuration revision
    Producer->>Kafka: Publish orders with that revision
    Kafka-->>Ingest: Deliver payload and Kafka coordinates
    Ingest->>PG: BEGIN; insert valid/rejected records
    PG-->>Ingest: COMMIT succeeds
    Ingest->>Kafka: Commit explicit offsets
    Note over Ingest,PG: Failed writes leave offsets uncommitted; redelivery is deduplicated

    loop Approximately every five seconds
        Monitor->>PG: BEGIN REPEATABLE READ; acquire evaluation lock
        Monitor->>PG: Read bounded windows and effective contract versions
        Monitor->>Rule: Evaluate snapshot against supported rules
        Rule-->>Monitor: Healthy / warming up / stale / violation
        Monitor->>PG: Persist evaluation
        opt Violation without an existing active episode
            Monitor->>PG: Capture source context; insert snapshot, incident and timeline
        end
        Monitor->>PG: COMMIT evaluation and capture together
    end
    Engineer->>API: GET incident and evidence
    API->>PG: Select recorded incident and immutable snapshot
    PG-->>API: Return captured records
    API-->>Engineer: Return JSON evidence
    Note over Monitor,PG: Later configuration changes do not replace captured evidence
```

No model call or engineer action is required to create an incident. Stale transport and insufficient samples suppress new signals. Resolution remains pending until the later remediation slice can verify fresh post-action events.
