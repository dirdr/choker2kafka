# Sentinel system context

Sentinel is a contract-monitoring system for a platform engineer. The current implementation publishes a controlled synthetic stream and records violations. Investigation, approval and repair remain planned.

```mermaid
C4Context
    title Sentinel system context — implemented slices
    Person(engineer, "Platform engineer", "Reviews stream state and evidence")
    System(sentinel, "Sentinel", "Monitors semantic Kafka contracts")
    System_Ext(kafka, "Aiven Kafka", "Carries the controlled orders stream")
    System_Ext(postgres, "Aiven PostgreSQL", "Stores configuration and evidence")
    System_Ext(anthropic, "Anthropic API", "Readiness and bounded Claude investigation")
    Rel(engineer, sentinel, "Reads evidence and changes producer settings", "JSON / HTTPS")
    Rel(sentinel, kafka, "Publishes and consumes orders", "Kafka / TLS")
    Rel(sentinel, postgres, "Persists events and incident records", "PostgreSQL / TLS")
    Rel(sentinel, anthropic, "Investigates frozen incident evidence", "Anthropic API / HTTPS")
```

The engineer controls producer configuration through an authenticated API. Contract expectations are versioned independently of that configuration. A producer change cannot silently change the expected unit.
