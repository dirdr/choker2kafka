import os
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from confluent_kafka import KafkaError, KafkaException
from pydantic import ValidationError
from support import request

from sentinel.main import app, lifespan
from sentinel.stream.domain import (
    ConfigurationChange,
    OrderEvent,
    ProducerConfiguration,
    RevisionConflict,
    StreamRecord,
    TimestampUnit,
    make_order,
    transport_status,
)
from sentinel.stream.kafka import KafkaStream
from sentinel.stream.service import StreamWorker


def configuration(unit=TimestampUnit.MILLISECONDS, revision=1):
    return ProducerConfiguration(revision=revision, event_time_unit=unit)


def record(partition=0, offset=0, payload=b"{}"):
    return StreamRecord(
        "orders", partition, offset, 1_000, "create_time", payload, datetime.now(UTC)
    )


class DomainTests(unittest.TestCase):
    def test_timestamp_serialization_tracks_configuration(self):
        now = 1_800_000_000_123_456_789
        for unit, expected in (
            (TimestampUnit.SECONDS, 1_800_000_000),
            (TimestampUnit.MILLISECONDS, 1_800_000_000_123),
            (TimestampUnit.MICROSECONDS, 1_800_000_000_123_456),
        ):
            with self.subTest(unit=unit):
                event = make_order(configuration(unit, 8), "build-123", now)
                self.assertEqual(event.event_time, expected)
                self.assertEqual(event.config_revision, 8)
                self.assertEqual(event.code_version, "build-123")
                self.assertEqual(
                    OrderEvent.model_validate_json(event.model_dump_json()), event
                )

    def test_event_ids_are_unique(self):
        first, second = [make_order(configuration(), "test", 1) for _ in range(2)]
        self.assertNotEqual(first.event_id, second.event_id)
        self.assertNotEqual(first.order_id, second.order_id)

    def test_invalid_event_time_does_not_enter_storage(self):
        event = make_order(configuration(), "test").model_dump(mode="json")
        for value in (True, "1800000000000", 1.5, 2**63, -(2**63) - 1):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                OrderEvent.model_validate({**event, "event_time": value})

    def test_changes_are_bounded(self):
        valid = {
            "expected_revision": 1,
            "event_time_unit": "seconds",
            "reason": "Unit change",
        }
        for extra in (
            {"event_time_unit": "hours"},
            {"expected_revision": 0},
            {"expected_revision": True},
            {"reason": ""},
            {"other_field": 1},
        ):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                ConfigurationChange.model_validate({**valid, **extra})

    def test_freshness_does_not_report_empty_or_stale_transport_as_flowing(self):
        now = datetime.now(UTC)
        self.assertEqual(transport_status(None, now), "warming_up")
        self.assertEqual(transport_status(now - timedelta(seconds=10), now), "flowing")
        self.assertEqual(transport_status(now - timedelta(seconds=11), now), "stale")


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.repository.configuration.return_value = configuration()
        self.stream = MagicMock()
        self.stream.receive.return_value = []
        self.worker = StreamWorker(self.repository, self.stream, "test")

    def test_commit_occurs_after_successful_storage(self):
        records = [record()]
        calls = []
        self.stream.receive.return_value = records
        self.repository.store.side_effect = lambda value: calls.append("store")
        self.stream.acknowledge.side_effect = lambda value: calls.append("commit")
        self.worker.step()
        self.assertEqual(calls, ["store", "commit"])
        self.repository.store.assert_called_once_with(records)

    def test_failed_storage_leaves_offsets_uncommitted(self):
        self.stream.receive.return_value = [record()]
        self.repository.store.side_effect = OSError("database unavailable")
        with self.assertRaises(OSError):
            self.worker.step()
        self.stream.acknowledge.assert_not_called()

    def test_producer_reloads_configuration_between_batches(self):
        with patch("sentinel.stream.service.monotonic", side_effect=[1, 1.5, 2]):
            self.worker.step()
            self.worker.step()
            self.repository.configuration.return_value = configuration(
                TimestampUnit.SECONDS, 2
            )
            self.worker.step()
        batches = [call.args[0] for call in self.stream.publish.call_args_list]
        self.assertEqual([len(batch) for batch in batches], [10, 10])
        self.assertEqual(batches[0][0].config_revision, 1)
        self.assertEqual(batches[1][0].config_revision, 2)
        self.assertLess(batches[1][0].event_time, batches[0][0].event_time // 100)

    def test_failure_closes_consumer_before_retry(self):
        self.stream.receive.side_effect = OSError("connection lost")
        self.stream.close.side_effect = self.worker.stop
        self.worker.run()
        self.stream.close.assert_called_once()
        self.assertEqual(self.worker.status()["worker"], "stopped")


class KafkaTests(unittest.TestCase):
    def setUp(self):
        self.stream = KafkaStream("orders", "test-group")
        self.stream.producer = MagicMock()
        self.stream.producer.flush.return_value = 0
        self.stream.consumer = MagicMock()

    def test_explicit_offsets_are_committed_for_every_partition(self):
        self.stream.consumer.commit.return_value = []
        self.stream.acknowledge([record(0, 3), record(1, 8), record(0, 7)])
        call = self.stream.consumer.commit.call_args
        self.assertFalse(call.kwargs["asynchronous"])
        self.assertEqual(
            {(offset.partition, offset.offset) for offset in call.kwargs["offsets"]},
            {(0, 8), (1, 9)},
        )

    def test_partition_commit_failure_is_not_ignored(self):
        partition = SimpleNamespace(error=KafkaError(KafkaError._TIMED_OUT))
        self.stream.consumer.commit.return_value = [partition]
        with self.assertRaises(KafkaException):
            self.stream.acknowledge([record()])

    def test_delivery_failure_is_not_success(self):
        def fail_delivery(*args, **kwargs):
            kwargs["on_delivery"](KafkaError(KafkaError._MSG_TIMED_OUT), None)

        self.stream.producer.produce.side_effect = fail_delivery
        with self.assertRaises(KafkaException):
            self.stream.publish([make_order(configuration(), "test")])

    def test_pending_deliveries_are_not_success(self):
        self.stream.producer.flush.return_value = 1
        with self.assertRaises(TimeoutError):
            self.stream.publish([make_order(configuration(), "test")])

    def test_received_record_preserves_kafka_provenance(self):
        message = MagicMock()
        message.error.return_value = None
        message.timestamp.return_value = (2, 1800000000123)
        message.topic.return_value = "orders"
        message.partition.return_value = 2
        message.offset.return_value = 19
        message.value.return_value = b'{"event_time":1800000000}'
        self.stream.consumer.consume.return_value = [message]
        result = self.stream.receive()[0]
        self.assertEqual((result.partition, result.offset), (2, 19))
        self.assertEqual(result.kafka_timestamp_type, "log_append_time")
        self.assertEqual(result.kafka_timestamp_ms, 1800000000123)
        self.assertEqual(result.payload, message.value())
        self.assertIsNotNone(result.ingested_at.tzinfo)

    def test_manual_commit_and_offset_storage_are_required(self):
        with (
            patch("sentinel.stream.kafka.kafka_configuration", return_value={}),
            patch("sentinel.stream.kafka.AdminClient") as admin,
            patch("sentinel.stream.kafka.Producer"),
            patch("sentinel.stream.kafka.Consumer") as consumer,
        ):
            admin.return_value.list_topics.return_value.topics = {
                "orders": MagicMock(error=None)
            }
            self.stream.open()
            config = consumer.call_args.args[0]
            self.assertFalse(config["enable.auto.commit"])
            self.assertFalse(config["enable.auto.offset.store"])
            self.assertEqual(config["auto.offset.reset"], "earliest")


class StreamApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.repository.configuration.return_value = configuration()
        self.repository.change_configuration.return_value = configuration(
            TimestampUnit.SECONDS, 2
        )
        app.state.repository = self.repository
        self.environment = patch.dict(os.environ, {"OPERATOR_TOKEN": "operator-secret"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(lambda: delattr(app.state, "repository"))

    def change(self):
        return {
            "expected_revision": 1,
            "event_time_unit": "seconds",
            "reason": "Test configuration change",
        }

    async def test_configuration_mutation_requires_operator(self):
        for token in (None, "wrong-token"):
            with self.subTest(token=token):
                status, _ = await request(
                    app, "/api/producer/configuration", "PATCH", self.change(), token
                )
                self.assertEqual(status, 401)
        self.repository.change_configuration.assert_not_called()

    async def test_mutation_is_disabled_without_operator_token(self):
        os.environ["OPERATOR_TOKEN"] = ""
        status, _ = await request(
            app, "/api/producer/configuration", "PATCH", self.change(), "anything"
        )
        self.assertEqual(status, 503)
        self.repository.change_configuration.assert_not_called()

    async def test_operator_can_update_a_revision(self):
        status, body = await request(
            app,
            "/api/producer/configuration",
            "PATCH",
            self.change(),
            "operator-secret",
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["revision"], 2)
        self.assertEqual(body["event_time_unit"], "seconds")

    async def test_stale_revision_returns_conflict(self):
        self.repository.change_configuration.side_effect = RevisionConflict
        status, _ = await request(
            app,
            "/api/producer/configuration",
            "PATCH",
            self.change(),
            "operator-secret",
        )
        self.assertEqual(status, 409)

    async def test_unsupported_fields_cannot_be_mutated(self):
        status, _ = await request(
            app,
            "/api/producer/configuration",
            "PATCH",
            {**self.change(), "topic": "other"},
            "operator-secret",
        )
        self.assertEqual(status, 422)
        self.repository.change_configuration.assert_not_called()

    async def test_event_reads_are_bounded(self):
        for query in (b"limit=0", b"limit=101"):
            status, _ = await request(app, "/api/events", query=query)
            self.assertEqual(status, 422)
        self.repository.recent_events.assert_not_called()

    async def test_worker_is_stopped_on_shutdown(self):
        self.addCleanup(lambda: delattr(app.state, "stream_worker"))
        with (
            patch.dict(os.environ, {"STREAM_ENABLED": "true"}),
            patch("sentinel.main.StreamWorker") as worker,
        ):
            async with lifespan(app):
                self.assertEqual(app.state.stream_worker, worker.return_value)
            worker.return_value.stop.assert_called_once()
