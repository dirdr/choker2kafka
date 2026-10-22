import assert from "node:assert/strict";

function elapsed(start, end) {
  const value = Date.parse(end) - Date.parse(start);
  return Number.isFinite(value) && value >= 0 ? value / 1000 : null;
}

export async function collectEvidence(read, incidentId) {
  assert.match(incidentId, /^[0-9a-f-]{36}$/i, "Provide a valid incident ID");
  const [incident, runs, captured, repair, history] = await Promise.all([
    read(`/api/incidents/${incidentId}`),
    read(`/api/incidents/${incidentId}/investigations`),
    read(`/api/incidents/${incidentId}/evidence`),
    read(`/api/incidents/${incidentId}/repair`),
    read("/api/producer/configuration/history"),
  ]);
  assert.equal(incident.status, "resolved", "Resolve the incident before exporting evidence");
  assert.equal(repair.status, "verified", "The repair must have verified recovery");
  assert.match(repair.pr_url || "", /^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/pull\/\d+$/);
  const attempt = runs.find((run) => run.investigation_id === repair.investigation_id);
  assert.ok(attempt, "The repair's investigation must be available");
  const run = await read(`/api/investigations/${attempt.investigation_id}`);
  assert.equal(run.status, "completed");
  assert.equal(run.finding?.conclusion, "supported");
  const windows = [...repair.recovery_windows].sort((a, b) => Date.parse(a.window_end) - Date.parse(b.window_end));
  assert.equal(windows.length, 2, "Two recovery windows must be recorded");
  assert.ok(windows.every((window) => window.passed && window.configuration_revision === repair.recovery_revision));
  assert.equal(Date.parse(windows[0].window_end), Date.parse(windows[1].window_start), "Recovery windows must be adjacent and non-overlapping");
  const body = captured.body;
  const revision = incident.configuration_revision;
  const faulty = body.producer_configuration_history.find((item) => item.revision === revision);
  const fixed = history.find((item) => item.revision === repair.recovery_revision);
  assert.ok(faulty, "The captured faulty revision is required");
  const signal = body.evaluation.signal;
  const events = body.snapshot.events.filter((event) => event.config_revision === revision && Date.parse(event.ingested_at) >= Date.parse(signal.window_start) && Date.parse(event.ingested_at) < Date.parse(signal.window_end));
  assert.ok(events.length, "The captured failing window must contain events");
  const accepted = events.filter((event) => Number.isSafeInteger(event.event_time)).length;
  const tokens = run.usage && Number.isFinite(run.usage.input_tokens) && Number.isFinite(run.usage.output_tokens)
    ? run.usage.input_tokens + run.usage.output_tokens : null;
  return {
    exported_at: new Date().toISOString(), incident, run, repair, faulty, fixed, captured,
    baseline: {name: "Integer type check", accepted, samples: events.length},
    contract: {status: body.evaluation.status, failure_ratio: body.evaluation.metrics.failure_ratio},
    metrics: {
      detection_seconds: elapsed(faulty.changed_at, incident.opened_at),
      investigation_seconds: Number.isFinite(run.duration_ms) ? run.duration_ms / 1000 : null,
      reported_tokens: tokens,
      recovery_seconds: fixed ? elapsed(fixed.changed_at, incident.resolved_at) : null,
      model_requests: run.usage?.requests ?? null,
      tool_calls: run.usage?.tool_calls ?? null,
    },
  };
}
