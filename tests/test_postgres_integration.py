import os
import unittest
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from psycopg import IntegrityError, sql

from sentinel.stream.domain import (
    ConfigurationChange,
    RevisionConflict,
    StreamRecord,
    make_order,
)
from sentinel.stream.postgres import PostgresRepository


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "Set TEST_DATABASE_URL to a dedicated PostgreSQL test database",
)
class PostgresIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ, {"DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.repository = PostgresRepository()
        self.repository.initialize()
        self.topic = f"test-{uuid4()}"
        self.addCleanup(self.clean_events)

    def clean_events(self):
        with self.repository.connection() as connection:
            for table in ("events", "rejected_records"):
                connection.execute(
                    sql.SQL("DELETE FROM sentinel.{} WHERE topic = %s").format(
                        sql.Identifier(table)
                    ),
                    (self.topic,),
                )

    def record(self, payload, offset=0):
        return StreamRecord(
            self.topic,
            0,
            offset,
            1800000000123,
            "create_time",
            payload,
            datetime.now(UTC),
        )

    def test_migrations_preserve_configuration_on_restart(self):
        before = self.repository.configuration()
        self.repository.initialize()
        self.assertEqual(self.repository.configuration(), before)

    def test_configuration_revision_and_history_are_atomic(self):
        before = self.repository.configuration()
        change = ConfigurationChange(
            expected_revision=before.revision,
            event_time_unit="seconds",
            reason="Integration test",
        )
        after = self.repository.change_configuration(change)
        self.assertEqual(after.revision, before.revision + 1)
        with self.assertRaises(RevisionConflict):
            self.repository.change_configuration(change)
        self.assertEqual(self.repository.configuration(), after)
        latest = self.repository.configuration_history()[0]
        self.assertEqual(latest["revision"], after.revision)
        self.assertEqual(latest["previous_unit"], before.event_time_unit)
        self.assertEqual(latest["actor"], "operator")

    def test_redelivery_and_duplicate_event_ids_do_not_duplicate_events(self):
        event = make_order(self.repository.configuration(), "integration")
        record = self.record(event.model_dump_json().encode())
        self.repository.store([record])
        self.repository.store([record, self.record(record.payload, offset=1)])
        with self.repository.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM sentinel.events WHERE topic = %s", (self.topic,)
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["config_revision"], event.config_revision)
        self.assertEqual(rows[0]["ingested_at"], record.ingested_at)
        self.assertEqual(rows[0]["kafka_timestamp_type"], "create_time")

    def test_malformed_records_do_not_block_valid_records(self):
        event = make_order(self.repository.configuration(), "integration")
        rejected = self.record(b"not-json")
        self.repository.store(
            [
                rejected,
                self.record(event.model_dump_json().encode(), offset=1),
            ]
        )
        self.repository.store([rejected])
        with self.repository.connection() as connection:
            invalid = connection.execute(
                "SELECT * FROM sentinel.rejected_records WHERE topic = %s",
                (self.topic,),
            ).fetchall()
            valid = connection.execute(
                "SELECT count(*) AS count FROM sentinel.events WHERE topic = %s",
                (self.topic,),
            ).fetchone()
        self.assertEqual(len(invalid), 1)
        self.assertEqual(bytes(invalid[0]["payload"]), b"not-json")
        self.assertEqual(valid["count"], 1)

    def test_batch_failure_rolls_back_events_before_offset_commit(self):
        event = make_order(self.repository.configuration(), "integration")
        invalid = StreamRecord(self.topic, 0, 1, None, "unavailable", b"not-json", None)
        with self.assertRaises(IntegrityError):
            self.repository.store(
                [self.record(event.model_dump_json().encode()), invalid]
            )
        with self.repository.connection() as connection:
            row = connection.execute(
                "SELECT count(*) AS count FROM sentinel.events WHERE topic = %s",
                (self.topic,),
            ).fetchone()
        self.assertEqual(row["count"], 0)
