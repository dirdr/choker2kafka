import assert from "node:assert/strict";
import { test } from "node:test";
import { fixtures } from "./fixtures.mjs";
import { collectEvidence } from "./evidence-data.mjs";

function completedFixture() {
  const fixture = fixtures();
  const id = fixture.incident.incident_id;
  const at = (seconds) => new Date(Date.parse(fixture.incident.opened_at) + seconds * 1000).toISOString();
  const faulty = { revision: 2, event_time_unit: "seconds", changed_at: at(-15), source_commit: "faulty-source" };
  fixture.incident.status = "resolved";
  fixture.incident.resolved_at = at(70);
  fixture.run.status = "completed";
  fixture.run.finding = fixture.finding;
  fixture.data[`/api/incidents/${id}/evidence`] = {body: {
    producer_configuration_history: [faulty],
    evaluation: {status: "violated", metrics: {failure_ratio: 1}, signal: {window_start: at(-10), window_end: at(0)}},
    snapshot: {events: [{config_revision: 2, event_time: 1792670400, ingested_at: at(-1)}]},
  }};
  fixture.data[`/api/incidents/${id}/repair`] = {
    status: "verified", pr_url: "https://github.com/dirdr/choker2kafka/pull/1",
    investigation_id: fixture.run.investigation_id, recovery_revision: 3,
    recovery_windows: [
      {passed: true, configuration_revision: 3, window_start: at(50), window_end: at(60)},
      {passed: true, configuration_revision: 3, window_start: at(60), window_end: at(70)},
    ],
  };
  fixture.data["/api/producer/configuration/history"] = [{revision: 3, changed_at: at(45)}];
  return {fixture, id, read: async (path) => structuredClone(fixture.data[path])};
}

test("export measurements use the recorded run and defined time boundaries", async () => {
  const {fixture, id, read} = completedFixture();
  const evidence = await collectEvidence(read, id);
  assert.equal(evidence.metrics.detection_seconds, 15);
  assert.equal(evidence.metrics.recovery_seconds, 25);
  assert.equal(evidence.metrics.investigation_seconds, fixture.run.duration_ms / 1000);
  assert.equal(evidence.metrics.reported_tokens, 10070);
  assert.equal(evidence.baseline.accepted, 1);
});

test("export refuses an open incident or an unverified repair", async () => {
  const {fixture, id, read} = completedFixture();
  fixture.incident.status = "open";
  await assert.rejects(collectEvidence(read, id), /Resolve the incident/);
  fixture.incident.status = "resolved";
  fixture.data[`/api/incidents/${id}/repair`].status = "merged";
  await assert.rejects(collectEvidence(read, id), /verified recovery/);
});

test("overlapping recovery windows cannot support the evidence report", async () => {
  const {fixture, id, read} = completedFixture();
  fixture.data[`/api/incidents/${id}/repair`].recovery_windows[1].window_start = fixture.incident.opened_at;
  await assert.rejects(collectEvidence(read, id), /non-overlapping/);
});
