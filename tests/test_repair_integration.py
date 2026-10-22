import os
import unittest
from datetime import timedelta

import test_detection_integration as detection_tests
from test_investigation import finding
from test_repair import FakeGitHub

from sentinel.detection.detectors import evaluate
from sentinel.investigation.domain import CapturedEvidence
from sentinel.investigation.postgres import InvestigationRepository
from sentinel.investigation.settings import MODEL_ID
from sentinel.producer.domain import ProducerFile, SourceFile
from sentinel.producer.postgres import ProducerRepository
from sentinel.repair.postgres import RepairRepository
from sentinel.repair.recovery import verify_recovery
from sentinel.repair.service import RepairWorker
from sentinel.stream.domain import StreamRecord, make_order


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "Set TEST_DATABASE_URL to a dedicated PostgreSQL test database",
)
class RepairIntegrationTests(unittest.TestCase):
    seed_regression = detection_tests.DetectionIntegrationTests.seed_regression
    incidents = detection_tests.DetectionIntegrationTests.incidents

    def setUp(self):
        detection_tests.DetectionIntegrationTests.setUp(self)
        self.seed_regression()
        self.config = self.storage.configuration()
        with self.storage.connection() as connection:
            connection.execute(
                "UPDATE sentinel.producer_configuration_history SET source_commit = 'bad-commit', source_file_sha = 'bad-blob' WHERE producer_id = 'checkout' AND revision = %s",
                (self.config.revision,),
            )
        self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        self.incident = self.incidents()[0]
        self.investigations = InvestigationRepository(self.storage)
        self.investigations.enqueue(MODEL_ID, 50000, self.topic)
        run = self.investigations.claim()
        captured = CapturedEvidence(
            str(run["snapshot_id"]), self.investigations.evidence(run["snapshot_id"])
        )
        captured.read("inspect_incident")
        captured.read("lookup_producer_context")
        result = finding(captured).model_copy(
            update={"affected_consumers": ["order-rate-dashboard"]}
        )
        captured.validate(result)
        self.investigations.finish(
            run["investigation_id"],
            result.model_dump(mode="json"),
            {"requests": 2},
            100,
        )
        self.repairs = RepairRepository(self.storage)
        self.github = FakeGitHub()
        self.repairs.propose(self.github)
        self.repair = self.repairs.detail(self.incident["incident_id"])

    def merge(self):
        self.repairs.update(
            self.repair,
            "merged",
            pr={
                "number": 1,
                "html_url": "https://github.com/dirdr/choker2kafka/pull/1",
                "file_sha": "fixed-blob",
            },
            merge_commit="merge-commit",
        )
        self.repair = self.repairs.detail(self.incident["incident_id"])
        ProducerRepository(self.storage).apply(
            SourceFile(
                ProducerFile(producer_id="checkout", event_time_unit="milliseconds"),
                "fixed-blob",
                "merge-commit",
                self.github.repository,
                self.github.branch,
            )
        )
        self.fixed = self.storage.configuration()

    def window(self, end, offset):
        start = end - timedelta(seconds=10)
        records = []
        for index in range(100):
            at = start + timedelta(seconds=index * 0.09)
            event = make_order(
                self.fixed, "merge-commit", int(at.timestamp() * 1_000_000_000)
            )
            records.append(
                StreamRecord(
                    self.topic,
                    0,
                    offset + index,
                    int(at.timestamp() * 1000),
                    "create_time",
                    event.model_dump_json().encode(),
                    at,
                )
            )
        self.storage.store(records)

    def test_pr_creation_is_durable_and_does_not_resolve_the_incident(self):
        RepairWorker(self.repairs).process(self.github, self.repair)
        saved = self.repairs.detail(self.incident["incident_id"])
        self.assertEqual(saved["status"], "open")
        self.assertEqual(saved["pr_number"], 1)
        self.assertEqual(self.incidents()[0]["status"], "open")
        self.repairs.propose(self.github)
        self.assertEqual(
            self.repairs.detail(self.incident["incident_id"])["repair_id"],
            saved["repair_id"],
        )

    def test_resolution_requires_two_distinct_fresh_windows_after_source_sync(self):
        self.merge()
        end = (self.now + timedelta(seconds=60)).replace(microsecond=0)
        end = end.replace(second=end.second - end.second % 10)
        self.window(end, 1000)
        first = verify_recovery(self.storage, self.repair, end + timedelta(seconds=1))
        self.assertEqual(first["status"], "checking")
        verify_recovery(self.storage, self.repair, end + timedelta(seconds=1))
        self.assertEqual(
            len(self.repairs.detail(self.incident["incident_id"])["recovery_windows"]),
            1,
        )
        self.assertEqual(self.incidents()[0]["status"], "open")
        self.window(end + timedelta(seconds=10), 2000)
        second = verify_recovery(self.storage, self.repair, end + timedelta(seconds=11))
        self.assertEqual(second["status"], "verified")
        self.assertEqual(
            self.repairs.detail(self.incident["incident_id"])["status"], "verified"
        )
        self.assertEqual(self.incidents()[0]["status"], "resolved")

    def test_healthy_data_without_a_merged_pr_is_not_verified(self):
        result = verify_recovery(self.storage, self.repair, self.now)
        self.assertEqual(result["status"], "waiting")
        self.assertEqual(self.incidents()[0]["status"], "open")

    def test_merge_without_applying_the_repaired_source_does_not_resolve(self):
        self.repairs.update(
            self.repair, "merged", pr={"number": 1, "file_sha": "fixed-blob"}
        )
        self.repair = self.repairs.detail(self.incident["incident_id"])
        self.assertEqual(
            verify_recovery(self.storage, self.repair, self.now)["status"],
            "awaiting_source_sync",
        )
        self.assertEqual(self.incidents()[0]["status"], "open")
