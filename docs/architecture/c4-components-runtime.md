# Sentinel runtime components

This view shows execution flow for the implemented slices. Every box inside the Runtime boundary runs in the same Python process. The arrows describe runtime calls and data movement.

```mermaid
flowchart TB
    accTitle: Sentinel runtime architecture
    accDescr: The producer reads PostgreSQL configuration and publishes orders to Kafka. Ingestion persists records before committing Kafka offsets. A separate detector reads bounded windows and effective contracts, evaluates pure rules, and atomically records incidents and immutable evidence. FastAPI exposes status and recorded evidence.

    operator["Platform engineer<br/>Person · API client"]
    subgraph runtime["Sentinel application · Aiven Runtime · Python / FastAPI"]
        api["HTTP adapter<br/>FastAPI · Read APIs and protected config changes"]
        subgraph stream["Stream application worker · Background thread"]
            producer["Configured producer<br/>Ten orders per batch · Reloads revisions"]
            consumer["Ingestion service<br/>Validates and batches consumed records"]
        end
        monitor["Detection application worker<br/>Evaluates every five seconds"]
        domain["Domain rule registry<br/>Pure timestamp bounds detector"]
        streamrepo["Stream repository adapter<br/>psycopg · Config and event transactions"]
        capturerepo["Detection repository adapter<br/>psycopg · Snapshot and incident transaction"]
    end
    orders[["orders topic<br/>Aiven Kafka · TLS"]]
    database[("Aiven PostgreSQL<br/>Configuration · Contracts · Events<br/>Evaluations · Incidents · Frozen evidence")]

    operator -->|"Read APIs / operator bearer token · HTTPS"| api
    api -->|"Read events / change exact revision"| streamrepo
    api -->|"Read contracts / incidents / captured evidence"| capturerepo
    producer -->|"Read current producer configuration"| streamrepo
    producer -->|"Publish versioned orders · Kafka / TLS"| orders
    orders -->|"Deliver records with partition and offset"| consumer
    consumer -->|"Persist accepted and rejected records"| streamrepo
    consumer -->|"Commit offsets after database commit"| orders
    streamrepo -->|"Execute bounded SQL · PostgreSQL / TLS"| database
    monitor -->|"Load repeatable source snapshot"| capturerepo
    capturerepo -->|"Invoke detector with frozen window"| domain
    domain -->|"Return check result and generic signal"| capturerepo
    capturerepo -->|"Persist evaluation and new incident atomically · TLS"| database

    classDef app fill:#e8f0fb,stroke:#365b8c,color:#132d4e
    classDef adapter fill:#edf5ee,stroke:#4a7853,color:#173f21
    classDef domain fill:#fff3da,stroke:#a77a22,color:#523b0c
    classDef external fill:#f1f3f5,stroke:#66717e,color:#25303d
    class api,producer,consumer,monitor app
    class streamrepo,capturerepo adapter
    class domain domain
    class operator,orders,database external
```

The domain detector performs no I/O and no mutation. A signal identifies the rule, fields, window, observed/expected values and evidence IDs. The repository obtains a consistent source view and persists the result inside one transaction. A database uniqueness constraint suppresses repeated active episodes, and append-only triggers protect captured source versions and evidence.

The rule registry is an extension point for additional checks. The future action registry is a separate boundary: detecting a new rule will not automatically authorize a new kind of repair.
