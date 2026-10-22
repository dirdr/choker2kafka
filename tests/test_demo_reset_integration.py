import os
import unittest
from uuid import uuid4

import test_detection_integration as detection_tests

from sentinel.demo.reset import DemoReset
from sentinel.detection.detectors import evaluate
from sentinel.investigation.postgres import InvestigationRepository
from sentinel.investigation.settings import SettingsChange
from sentinel.stream.domain import StreamRecord, make_order


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "Set TEST_DATABASE_URL to a dedicated PostgreSQL test database",
)
class DemoResetIntegrationTests(unittest.TestCase):
    seed_regression = detection_tests.DetectionIntegrationTests.seed_regression
    incidents = detection_tests.DetectionIntegrationTests.incidents

    def setUp(self):
        detection_tests.DetectionIntegrationTests.setUp(self)
        self.seed_regression()
        self.repository.evaluate_and_capture(self.topic, evaluate, self.now)

    def count(self, table):
        with self.storage.connection() as connection:
            return connection.execute(
                f"SELECT count(*) AS count FROM sentinel.{table}"
            ).fetchone()["count"]

    def test_reset_clears_demo_evidence_preserves_settings_and_runs_once(self):
        investigations = InvestigationRepository(self.storage)
        current = investigations.settings()
        saved = investigations.update_settings(
            SettingsChange(
                expected_revision=current["revision"],
                model_id="claude-sonnet-4-6",
                token_limit=80000,
            )
        )
        reset_id = str(uuid4())
        reset = DemoReset(self.storage, None)
        result = reset.clear(
            reset_id, [{"topic": self.topic, "partition": 0, "offset": 10}]
        )
        self.assertEqual(result["status"], "completed")
        for table in (
            "incidents",
            "incident_snapshots",
            "contract_evaluations",
            "events",
            "producer_sources",
        ):
            self.assertEqual(self.count(table), 0)
        self.assertEqual(investigations.settings(), saved)
        self.assertEqual(self.storage.configuration().event_time_unit, "milliseconds")
        event = make_order(self.storage.configuration(), "after-reset")
        self.storage.store(
            [
                StreamRecord(
                    self.topic,
                    0,
                    10,
                    None,
                    "unavailable",
                    event.model_dump_json().encode(),
                    self.now,
                )
            ]
        )
        self.assertEqual(reset.clear(reset_id, [])["status"], "already_applied")
        self.assertEqual(self.count("events"), 1)

    def test_old_valid_and_rejected_records_cannot_repopulate_the_new_run(self):
        reset = DemoReset(self.storage, None)
        reset.clear(
            str(uuid4()), [{"topic": self.topic, "partition": 0, "offset": 1000}]
        )
        event = make_order(self.storage.configuration(), "retained")
        self.storage.store(
            [
                StreamRecord(
                    self.topic,
                    0,
                    99,
                    None,
                    "unavailable",
                    event.model_dump_json().encode(),
                    self.now,
                ),
                StreamRecord(
                    self.topic, 0, 100, None, "unavailable", b"invalid", self.now
                ),
            ]
        )
        self.assertEqual(self.count("events"), 0)
        self.assertEqual(self.count("rejected_records"), 0)
