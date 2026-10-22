import os
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from psycopg import Error
from psycopg.types.json import Jsonb

from sentinel.detection.detectors import evaluate
from sentinel.detection.postgres import DetectionRepository
from sentinel.stream.domain import ConfigurationChange, StreamRecord, make_order
from sentinel.stream.postgres import PostgresRepository


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "Set TEST_DATABASE_URL to a dedicated PostgreSQL test database",
)
class DetectionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ, {"DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.storage = PostgresRepository()
        self.repository = DetectionRepository(self.storage)
        self.topic = f"test-{uuid4()}"
        self.repository.initialize(self.topic)
        self.now = datetime.now(UTC) + timedelta(seconds=5)
        with self.storage.connection() as connection:
            connection.execute(
                "UPDATE sentinel.monitoring_runs SET started_at = %s WHERE topic = %s",
                (self.now - timedelta(minutes=5), self.topic),
            )

    def seed_regression(self):
        current = self.storage.configuration()
        baseline = self.storage.change_configuration(
            ConfigurationChange(
                expected_revision=current.revision,
                event_time_unit="milliseconds",
                reason="Integration baseline",
            )
        )
        faulty = self.storage.change_configuration(
            ConfigurationChange(
                expected_revision=baseline.revision,
                event_time_unit="seconds",
                reason="Integration regression",
            )
        )
        records = []
        for index in range(200):
            config = baseline if index < 100 else faulty
            age = 69 - index * 0.1 if index < 100 else 9 - (index - 100) * 0.08
            ingested = self.now - timedelta(seconds=age)
            event = make_order(
                config, "integration", int(ingested.timestamp() * 1_000_000_000)
            )
            records.append(
                StreamRecord(
                    self.topic,
                    0,
                    index,
                    int(ingested.timestamp() * 1000),
                    "create_time",
                    event.model_dump_json().encode(),
                    ingested,
                )
            )
        self.storage.store(records)

    def incidents(self):
        with self.storage.connection() as connection:
            return connection.execute(
                "SELECT * FROM sentinel.incidents WHERE topic = %s", (self.topic,)
            ).fetchall()

    def test_automatic_capture_and_duplicate_episode_suppression(self):
        self.seed_regression()
        first = self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        self.assertEqual(first[0].status, "violated")
        self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        self.repository.evaluate_and_capture(
            self.topic, evaluate, self.now + timedelta(seconds=5)
        )
        incidents = self.incidents()
        self.assertEqual(len(incidents), 1)
        captured = self.repository.evidence(incidents[0]["incident_id"])
        self.assertEqual(len(captured["body"]["snapshot"]["events"]), 200)
        self.assertEqual(captured["body"]["missing_configuration_revisions"], [])
        self.assertEqual(
            captured["body"]["producer_context_versions"][0]["provenance"],
            "seeded_synthetic_metadata",
        )
        self.assertEqual(
            len(self.repository.incident(incidents[0]["incident_id"])["timeline"]), 1
        )

    def test_snapshots_and_trigger_contract_survive_live_changes(self):
        self.seed_regression()
        self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        incident = self.incidents()[0]
        before = self.repository.evidence(incident["incident_id"])
        current = self.storage.configuration()
        self.storage.change_configuration(
            ConfigurationChange(
                expected_revision=current.revision,
                event_time_unit="milliseconds",
                reason="Integration restore",
            )
        )
        contract = self.repository.contracts(self.topic, 1)[0]["definition"]
        contract["version"] = 2
        contract["effective_from"] = (self.now + timedelta(seconds=1)).isoformat()
        contract["rules"][0]["parameters"]["unit"] = "seconds"
        with self.storage.connection() as connection:
            connection.execute(
                "INSERT INTO sentinel.contract_versions (contract_id, version, topic, effective_from, definition) VALUES (%s, 2, %s, %s, %s)",
                (
                    contract["contract_id"],
                    self.topic,
                    contract["effective_from"],
                    Jsonb(contract),
                ),
            )
        self.repository.evaluate_and_capture(
            self.topic, evaluate, self.now + timedelta(seconds=5)
        )
        self.assertEqual(self.repository.evidence(incident["incident_id"]), before)
        self.assertEqual(self.incidents()[0]["contract_version"], 1)

    def test_capture_failure_rolls_back_evaluation_and_incident(self):
        self.seed_regression()
        original = self.repository.record

        def fail_after_capture(*args):
            original(*args)
            raise RuntimeError("Simulated failure after timeline insert")

        with (
            patch.object(self.repository, "record", side_effect=fail_after_capture),
            self.assertRaises(RuntimeError),
        ):
            self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        self.assertEqual(self.incidents(), [])
        self.assertEqual(self.repository.status(self.topic), [])
        with self.storage.connection() as connection:
            row = connection.execute(
                "SELECT count(*) AS count FROM sentinel.incident_snapshots WHERE body->'snapshot'->>'topic' = %s",
                (self.topic,),
            ).fetchone()
        self.assertEqual(row["count"], 0)

    def test_captured_evidence_and_contract_versions_are_immutable(self):
        self.seed_regression()
        self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        incident = self.incidents()[0]
        with self.assertRaises(Error), self.storage.connection() as connection:
            connection.execute(
                "UPDATE sentinel.incident_snapshots SET body = '{}' WHERE snapshot_id = %s",
                (incident["snapshot_id"],),
            )
        with self.assertRaises(Error), self.storage.connection() as connection:
            connection.execute(
                "UPDATE sentinel.contract_versions SET definition = '{}' WHERE topic = %s",
                (self.topic,),
            )

    def test_restart_reuses_run_and_preserves_one_active_incident(self):
        self.seed_regression()
        self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        original = self.incidents()[0]
        restarted = DetectionRepository(self.storage)
        restarted.initialize(self.topic)
        restarted.evaluate_and_capture(
            self.topic, evaluate, self.now + timedelta(seconds=5)
        )
        self.assertEqual(
            [row["incident_id"] for row in self.incidents()], [original["incident_id"]]
        )

    def test_stale_stream_records_status_without_opening_incident(self):
        self.seed_regression()
        results = self.repository.evaluate_and_capture(
            self.topic, evaluate, self.now + timedelta(seconds=11)
        )
        self.assertEqual(results[0].status, "stale")
        self.assertEqual(self.incidents(), [])

    def test_missing_configuration_history_is_explicit_in_capture(self):
        self.seed_regression()
        with self.storage.connection() as connection:
            connection.execute(
                "UPDATE sentinel.events SET config_revision = 999999 WHERE topic = %s",
                (self.topic,),
            )
        self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        incident = self.incidents()[0]
        body = self.repository.evidence(incident["incident_id"])["body"]
        self.assertEqual(body["missing_configuration_revisions"], [999999])

    def test_distinct_contracts_can_reuse_local_rule_ids(self):
        self.seed_regression()
        contract = self.repository.contracts(self.topic, 1)[0]["definition"]
        contract["contract_id"] += ".second-policy"
        with self.storage.connection() as connection:
            connection.execute(
                "INSERT INTO sentinel.contract_versions (contract_id, version, topic, effective_from, definition) VALUES (%s, 1, %s, %s, %s)",
                (
                    contract["contract_id"],
                    self.topic,
                    contract["effective_from"],
                    Jsonb(contract),
                ),
            )
        self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        self.assertEqual(len(self.incidents()), 2)

    def test_fresh_healthy_data_does_not_rewrite_or_resolve_incident(self):
        self.seed_regression()
        self.repository.evaluate_and_capture(self.topic, evaluate, self.now)
        incident = self.incidents()[0]
        captured = self.repository.evidence(incident["incident_id"])
        current = self.storage.configuration()
        restored = self.storage.change_configuration(
            ConfigurationChange(
                expected_revision=current.revision,
                event_time_unit="milliseconds",
                reason="Integration restore",
            )
        )
        records = []
        for index in range(200):
            ingested = self.now + timedelta(seconds=1 + index * 0.08)
            event = make_order(
                restored, "integration", int(ingested.timestamp() * 1_000_000_000)
            )
            records.append(
                StreamRecord(
                    self.topic,
                    0,
                    200 + index,
                    int(ingested.timestamp() * 1000),
                    "create_time",
                    event.model_dump_json().encode(),
                    ingested,
                )
            )
        self.storage.store(records)
        results = self.repository.evaluate_and_capture(
            self.topic, evaluate, self.now + timedelta(seconds=20)
        )
        self.assertEqual(results[0].status, "healthy")
        self.assertEqual(self.incidents()[0]["status"], "open")
        self.assertEqual(self.repository.evidence(incident["incident_id"]), captured)
