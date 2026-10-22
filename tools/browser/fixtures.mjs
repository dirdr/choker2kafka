export function fixtures() {
  const incidentId = "128cb83b-0023-4c50-979f-431c6e366a37";
  const runId = "74eaf5aa-48c3-47b9-bdad-2b0d35e20519";
  const capturedAt = "2026-10-22T12:00:00Z";
  const incident = {
    incident_id: incidentId,
    run_id: "d120c2fc-5b18-47cb-8538-e1f4c1af1268",
    topic: "orders",
    producer_id: "checkout",
    rule_id: "event-time-semantics",
    affected_fields: ["event_time"],
    contract_id: "orders.checkout",
    contract_version: 1,
    status: "open",
    configuration_revision: 2,
    investigation_status: "failed",
    model_id: "claude-haiku-4-5-20251001",
    summary: null,
    opened_at: capturedAt,
    snapshot_id: "a120c2fc-5b18-47cb-8538-e1f4c1af1268",
    signal: { observed: { failure_ratio: 1 } },
    timeline: [],
  };
  const run = {
    investigation_id: runId,
    incident_id: incidentId,
    status: "failed",
    model_id: "claude-haiku-4-5-20251001",
    agent_version: "investigator-v2",
    token_limit: 50000,
    deadline_seconds: 120,
    created_at: capturedAt,
    started_at: capturedAt,
    finished_at: capturedAt,
    duration_ms: 19500,
    error_code: "invalid_model_output",
    error_detail: {
      message: "The model returned an invalid finding",
      fields: [{ path: "alternatives", type: "list_type" }],
    },
    usage: {
      requests: 2,
      tool_calls: 3,
      input_tokens: 9360,
      output_tokens: 710,
    },
    activity: [
      {
        activity_id: "b020c2fc-5b18-47cb-8538-e1f4c1af1268",
        tool_call_id: "inspect",
        tool_name: "inspect_incident",
        phase: "started",
        recorded_at: capturedAt,
      },
      {
        activity_id: "b120c2fc-5b18-47cb-8538-e1f4c1af1268",
        tool_call_id: "inspect",
        tool_name: "inspect_incident",
        phase: "returned",
        recorded_at: capturedAt,
        document_count: 12,
        body_bytes: 8000,
        snapshot_id: incident.snapshot_id,
      },
    ],
  };
  const contract = {
    contract_id: "orders.checkout",
    version: 1,
    topic: "orders",
    owner: "checkout-team",
    effective_from: "2026-01-01T00:00:00Z",
    rules: [
      {
        rule_id: "event-time-semantics",
        kind: "timestamp_bounds",
        fields: ["event_time"],
        parameters: {
          unit: "milliseconds",
          max_age_seconds: 60,
          max_future_seconds: 5,
        },
      },
    ],
  };
  const finding = {
    conclusion: "supported",
    likely_cause:
      "Configuration revision 2 emits seconds instead of milliseconds.",
    alternatives: ["Delayed delivery does not explain the scale change."],
    affected_consumers: ["order-rate-dashboard"],
    recommendation:
      "Restore milliseconds using a reviewed configuration change.",
    confidence: "high",
    confidence_rationale: "Captured records and configuration history agree.",
    evidence_ids: ["configuration:checkout:2"],
    attribution: { producer_id: "checkout", configuration_revision: 2 },
  };
  const configuration = {
    producer_id: "checkout",
    revision: 2,
    event_time_unit: "seconds",
  };
  const data = {
    "/api/stream": {
      worker: "running",
      transport: "flowing",
      recent_events: 100,
      recent_rejections: 0,
      last_ingested_at: capturedAt,
    },
    "/api/detection": {
      worker: "running",
      topic: "orders",
      checks: [
        {
          result: {
            status: "violated",
            recent_samples: 100,
            metrics: { failure_ratio: 1 },
          },
        },
      ],
    },
    "/api/investigation": {
      worker: "running",
      provider: "anthropic",
      model_id: run.model_id,
      agent_version: run.agent_version,
      token_limit: run.token_limit,
      deadline_seconds: run.deadline_seconds,
    },
    "/api/producer/configuration": configuration,
    "/api/incidents?limit=20": [incident],
    [`/api/incidents/${incidentId}`]: incident,
    [`/api/incidents/${incidentId}/investigations`]: [run],
    [`/api/investigations/${runId}`]: run,
    [`/api/investigations/${runId}?include_activity_bodies=true`]: {
      ...run,
      activity: [
        {
          ...run.activity[1],
          body: {
            documents: [
              { evidence_id: "configuration:checkout:2", data: configuration },
            ],
          },
        },
      ],
    },
    [`/api/incidents/${incidentId}/evidence`]: {
      snapshot_id: incident.snapshot_id,
      captured_at: capturedAt,
      body: { evaluation: { status: "violated" } },
    },
    "/api/contracts?limit=20": [contract],
    "/api/events?limit=20": [
      {
        event_id: "c120c2fc-5b18-47cb-8538-e1f4c1af1268",
        ingested_at: capturedAt,
        topic: "orders",
        producer_id: "checkout",
        payload: {event_time: 1792670400},
        config_revision: 2,
        partition: 0,
        kafka_offset: 123,
      },
    ],
    "/api/producer/configuration/history": [
      { revision: 2, new_event_time_unit: "seconds", reason: "Test fixture" },
    ],
  };
  return { data, incident, run, finding, configuration };
}
