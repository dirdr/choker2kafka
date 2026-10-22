import os
import unittest
from uuid import uuid4

import test_detection_integration as detection_tests
from psycopg import Error

from sentinel.detection.detectors import evaluate
from sentinel.investigation.agent import MODEL_ID
from sentinel.investigation.postgres import (
    InvestigationConflict,
    InvestigationRepository,
)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "Set TEST_DATABASE_URL to a dedicated PostgreSQL test database",
)
class InvestigationIntegrationTests(unittest.TestCase):
    seed_regression = detection_tests.DetectionIntegrationTests.seed_regression
    incidents = detection_tests.DetectionIntegrationTests.incidents

    def setUp(self):
        detection_tests.DetectionIntegrationTests.setUp(self)
        self.seed_regression()
        self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        self.incident = self.incidents()[0]
        self.investigations = InvestigationRepository(self.storage)
        self.investigations.enqueue(MODEL_ID, 20000, self.topic)
        self.run = self.investigations.claim()
        self.assertEqual(self.run["incident_id"], self.incident["incident_id"])
        self.addCleanup(self.finish_remaining)

    def finish_remaining(self):
        for run in self.investigations.list(self.incident["incident_id"]):
            if run["status"] == "queued":
                run = self.investigations.claim()
            self.investigations.finish(
                run["investigation_id"], None, {}, 0, "test_cleanup"
            )

    def test_queue_and_terminal_results_are_idempotent(self):
        self.investigations.enqueue(MODEL_ID, 20000, self.topic)
        self.assertEqual(len(self.investigations.list(self.incident["incident_id"])), 1)
        run_id = self.run["investigation_id"]
        self.assertEqual(self.run["snapshot_id"], self.incident["snapshot_id"])
        self.investigations.finish(
            run_id, {"conclusion": "insufficient_evidence"}, {"requests": 2}, 123
        )
        self.investigations.finish(run_id, None, {}, 0, "late_failure")
        saved = self.investigations.detail(run_id)
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(saved["duration_ms"], 123)
        self.assertEqual(self.incidents()[0]["status"], "open")
        with self.assertRaises(InvestigationConflict):
            self.investigations.retry(self.incident["incident_id"], MODEL_ID, 20000)

    def test_failed_run_retry_appends_and_reuses_snapshot(self):
        run_id = self.run["investigation_id"]
        self.investigations.finish(run_id, None, {"requests": 1}, 12, "TimeoutError")
        retry = self.investigations.retry(self.incident["incident_id"], MODEL_ID, 20000)
        self.assertNotEqual(retry["investigation_id"], run_id)
        self.assertEqual(retry["snapshot_id"], self.run["snapshot_id"])
        self.assertEqual(
            self.investigations.detail(run_id)["error_code"], "TimeoutError"
        )
        with self.assertRaises(InvestigationConflict):
            self.investigations.retry(self.incident["incident_id"], MODEL_ID, 20000)

    def test_restart_recovers_abandoned_run_without_repeating_paid_calls(self):
        with self.storage.connection() as connection:
            connection.execute(
                "UPDATE sentinel.investigations SET started_at = clock_timestamp() - interval '100 seconds' WHERE investigation_id = %s",
                (self.run["investigation_id"],),
            )
        self.assertIsNone(self.investigations.claim())
        saved = self.investigations.detail(self.run["investigation_id"])
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["error_code"], "interrupted")
        self.assertTrue(saved["retryable"])
        self.investigations.enqueue(MODEL_ID, 20000, self.topic)
        self.assertIsNone(self.investigations.claim())

    def test_tool_activity_is_live_and_append_only(self):
        run_id = self.run["investigation_id"]
        self.investigations.activity(
            run_id, "tool-1", "inspect_incident", "started", {"arguments": {}}
        )
        pending = self.investigations.detail(run_id)
        self.assertEqual(pending["status"], "running")
        self.assertEqual(pending["activity"][0]["phase"], "started")
        self.investigations.activity(
            run_id,
            "tool-1",
            "inspect_incident",
            "returned",
            {"snapshot_id": str(self.run["snapshot_id"])},
        )
        self.assertEqual(len(self.investigations.detail(run_id)["activity"]), 2)
        with self.assertRaises(Error), self.storage.connection() as connection:
            connection.execute(
                "DELETE FROM sentinel.investigation_activity WHERE investigation_id = %s",
                (run_id,),
            )

    def test_unknown_incident_does_not_enqueue_retry(self):
        self.assertIsNone(self.investigations.retry(uuid4(), MODEL_ID, 20000))
