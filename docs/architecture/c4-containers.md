# Sentinel containers

There is one deployable application, one Kafka topic and one database. Workers and detector functions are components within the application, rather than separate services.

```mermaid
C4Container
    title Sentinel container architecture
    Person(engineer, "Platform engineer", "Operates and inspects the stream")
    System_Boundary(sentinel, "Sentinel project on Aiven") {
        Container(app, "Sentinel application", "Python / FastAPI / Aiven Runtime", "HTTP API and background workers")
        ContainerQueue(orders, "orders topic", "Aiven Kafka", "Synthetic events and durable offsets")
        ContainerDb(database, "Sentinel database", "Aiven PostgreSQL", "Contracts, events and incident evidence")
    }
    System_Ext(anthropic, "Anthropic API", "Authentication check; investigator planned")
    Rel(engineer, app, "Reads status and submits configuration changes", "JSON / HTTPS")
    Rel(app, orders, "Publishes orders and consumes records", "Kafka / TLS")
    Rel(app, database, "Executes transactional parameterized queries", "psycopg / TLS")
    Rel(app, anthropic, "Checks credential access", "HTTPS")
```

One Runtime instance and one Uvicorn worker are the supported deployment shape. Two background threads keep ingestion and contract evaluation independent. The existing Grafana service will later read restricted PostgreSQL views; it will have no action-execution role.
