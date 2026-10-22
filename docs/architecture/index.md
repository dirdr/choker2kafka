# Sentinel architecture

These diagrams describe the implemented connectivity, ingestion, detection and investigation slices. The live fault-to-investigation journey still needs deployed verification. Implementation status and remaining work are tracked in [TODO.md](../../TODO.md).

| View | Question answered |
|---|---|
| [System context](c4-context.md) | Who interacts with Sentinel and which external systems does it connect to? |
| [Containers](c4-containers.md) | What is deployed, where does it run and which protocols connect it? |
| [Runtime components](c4-components-runtime.md) | How do production, ingestion, detection and capture work together? |
| [Incident capture sequence](c4-dynamic-capture.md) | What commits before Kafka offsets, and what is frozen when a rule fails? |
| [PostgreSQL records](data-model.md) | Which tables exist, what do they record and why? |

One Python application runs in Aiven Runtime with one Uvicorn worker. FastAPI serves the Tabler/Jinja workbench and API routes. Native JavaScript modules poll the same-origin APIs every five seconds. One background thread produces and ingests synthetic orders; a separate thread evaluates contracts, so ingestion failures cannot stop stale-stream checks. PostgreSQL is the sole durable application store. Kafka carries the events. A third background thread processes the durable investigation queue and runs bounded async model calls.

Domain models and pure checks live in `sentinel/detection/domain.py` and `detectors.py`. Application workers schedule work through small interfaces. PostgreSQL, Kafka and FastAPI adapters handle infrastructure. Contracts declare supported rule kinds and parameters; detector code supplies their behavior. Only `timestamp_bounds` is implemented.

Runtime injects credentials and certificate content through environment variables. Operator configuration changes require a bearer token. Secrets are not persisted in PostgreSQL. Consumer expectations are explicitly labelled synthetic metadata.

The investigator and bounded tools read frozen evidence and persist live tool activity and typed findings. See [investigation behavior](../investigations.md). The next planned components are proposal/approval policy, revision-checked action execution and deterministic recovery checks. They will run in the same application. Claude will propose corrections; application code will enforce authorization and establish recovery. The first workbench is implemented against current APIs, with manual operator controls and compact live investigation activity. Isolated re-investigation and read-only Grafana views remain pending.
