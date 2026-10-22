# Sentinel architecture

These diagrams describe the implemented connectivity, ingestion and detection slices. The detection slice still needs deployed verification. Implementation status and remaining work are tracked in [TODO.md](../../TODO.md).

| View | Question answered |
|---|---|
| [System context](c4-context.md) | Who interacts with Sentinel and which external systems does it connect to? |
| [Containers](c4-containers.md) | What is deployed, where does it run and which protocols connect it? |
| [Runtime components](c4-components-runtime.md) | How do production, ingestion, detection and capture work together? |
| [Incident capture sequence](c4-dynamic-capture.md) | What commits before Kafka offsets, and what is frozen when a rule fails? |
| [PostgreSQL records](data-model.md) | Which tables exist, what do they record and why? |

One Python application runs in Aiven Runtime with one Uvicorn worker. FastAPI handles requests on the event loop. One background thread produces and ingests synthetic orders; a separate thread evaluates contracts, so ingestion failures cannot stop stale-stream checks. PostgreSQL is the sole durable application store. Kafka carries the events.

Domain models and pure checks live in `sentinel/detection/domain.py` and `detectors.py`. Application workers schedule work through small interfaces. PostgreSQL, Kafka and FastAPI adapters handle infrastructure. Contracts declare supported rule kinds and parameters; detector code supplies their behavior. Only `timestamp_bounds` is implemented.

Runtime injects credentials and certificate content through environment variables. Operator configuration changes require a bearer token. Secrets are not persisted in PostgreSQL. Consumer expectations are explicitly labelled synthetic metadata.

The next planned components are the investigator and bounded evidence tools, proposal/approval policy, revision-checked action execution and deterministic recovery checks. They will run in the same application. Claude will propose corrections; application code will enforce authorization and establish recovery. The workbench, isolated re-investigation and read-only Grafana views follow those APIs.
