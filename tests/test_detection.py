import os
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

from detection_fixtures import NOW, contract, sample, snapshot
from psycopg import OperationalError
from support import request

from sentinel.detection.detectors import evaluate, plausible
from sentinel.detection.domain import TimestampBounds
from sentinel.detection.service import DetectionWorker
from sentinel.main import app, lifespan


class TimestampDetectorTests(unittest.TestCase):
    def result(self, source):
        return evaluate(source)[0]

    def test_healthy_milliseconds_do_not_create_signal(self):
        result = self.result(snapshot())
        self.assertEqual(result.status, "healthy")
        self.assertIsNone(result.signal)
        self.assertEqual((result.recent_samples, result.baseline_samples), (100, 100))

    def test_seconds_regression_has_conversion_and_revision_evidence(self):
        source = snapshot("seconds")
        result = self.result(source)
        self.assertEqual(result.status, "violated")
        self.assertEqual(result.metrics["failure_ratio"], 1)
        self.assertEqual(result.metrics["multiply_1000_plausible_ratio"], 1)
        self.assertEqual(result.metrics["divide_1000_plausible_ratio"], 0)
        self.assertAlmostEqual(result.metrics["median_scale_change"], 0.001, places=6)
        self.assertEqual(result.signal.contract_version, 1)
        self.assertEqual(result.signal.affected_fields, ("event_time",))
        self.assertIn(f"event:{source.events[-1].event_id}", result.signal.evidence_ids)

    def test_microseconds_regression_requires_division(self):
        result = self.result(snapshot("microseconds"))
        self.assertEqual(result.status, "violated")
        self.assertEqual(result.metrics["divide_1000_plausible_ratio"], 1)
        self.assertEqual(result.metrics["multiply_1000_plausible_ratio"], 0)

    def test_delayed_milliseconds_do_not_look_like_unit_conversion(self):
        source = snapshot()
        events = tuple(
            sample(event.ingested_at, lag_seconds=120)
            if event.ingested_at >= source.recent_start
            else event
            for event in source.events
        )
        result = self.result(source.model_copy(update={"events": events}))
        self.assertEqual(result.status, "violated")
        self.assertEqual(result.metrics["multiply_1000_plausible_ratio"], 0)
        self.assertEqual(result.metrics["divide_1000_plausible_ratio"], 0)

    def test_threshold_is_strictly_above_eighty_percent(self):
        for failed, expected in ((80, "healthy"), (81, "violated")):
            with self.subTest(failed=failed):
                source = snapshot()
                events = list(source.events)
                for index in range(100, 100 + failed):
                    events[index] = sample(events[index].ingested_at, "seconds")
                self.assertEqual(
                    self.result(
                        source.model_copy(update={"events": tuple(events)})
                    ).status,
                    expected,
                )

    def test_sample_minima_are_enforced(self):
        for recent, baseline, expected in (
            (49, 100, "warming_up"),
            (50, 99, "warming_up"),
            (50, 100, "healthy"),
        ):
            with self.subTest(recent=recent, baseline=baseline):
                result = self.result(
                    snapshot(recent_count=recent, baseline_count=baseline)
                )
                self.assertEqual(result.status, expected)
                self.assertIsNone(result.signal)

    def test_stale_transport_suppresses_new_signals(self):
        source = snapshot("seconds")
        for latest in (NOW - timedelta(seconds=10), None):
            with self.subTest(latest=latest):
                result = self.result(
                    source.model_copy(update={"last_received_at": latest})
                )
                self.assertEqual(result.status, "stale")
                self.assertIsNone(result.signal)

    def test_new_run_without_data_is_warming_up(self):
        source = snapshot().model_copy(
            update={
                "events": (),
                "last_received_at": None,
                "run_started_at": NOW - timedelta(seconds=2),
            }
        )
        self.assertEqual(self.result(source).status, "warming_up")

    def test_rejected_traffic_does_not_make_empty_valid_samples_healthy(self):
        source = snapshot().model_copy(update={"events": ()})
        self.assertEqual(self.result(source).status, "warming_up")

    def test_window_membership_uses_ingestion_time_and_excludes_end(self):
        source = snapshot()
        extra = (
            sample(source.baseline_start),
            sample(source.recent_start),
            sample(NOW),
            sample(source.baseline_start - timedelta(microseconds=1)),
        )
        result = self.result(
            source.model_copy(update={"events": source.events + extra})
        )
        self.assertEqual((result.recent_samples, result.baseline_samples), (101, 101))

    def test_extreme_business_times_stay_in_recent_window(self):
        source = snapshot()
        events = tuple(
            event.model_copy(update={"event_time": -(2**63)})
            if event.ingested_at >= source.recent_start
            else event
            for event in source.events
        )
        result = self.result(source.model_copy(update={"events": events}))
        self.assertEqual(result.status, "violated")
        self.assertEqual(result.recent_samples, 100)

    def test_effective_contract_is_selected_per_record(self):
        source = snapshot("seconds")
        accepted = contract("seconds", version=2, effective_from=source.recent_start)
        result = self.result(
            source.model_copy(update={"contracts": (*source.contracts, accepted)})
        )
        self.assertEqual(result.status, "healthy")
        self.assertEqual(result.contract_version, 2)

    def test_future_contract_does_not_redefine_current_expectation(self):
        source = snapshot("seconds")
        future = contract(
            "seconds", version=2, effective_from=NOW + timedelta(seconds=1)
        )
        self.assertEqual(
            self.result(
                source.model_copy(update={"contracts": (*source.contracts, future)})
            ).status,
            "violated",
        )

    def test_signal_preserves_contract_that_failed_before_policy_change(self):
        source = snapshot("seconds")
        changed = contract(
            "seconds", version=2, effective_from=NOW - timedelta(milliseconds=500)
        )
        result = self.result(
            source.model_copy(update={"contracts": (*source.contracts, changed)})
        )
        self.assertEqual(result.status, "violated")
        self.assertEqual(result.contract_version, 2)
        self.assertEqual(result.signal.contract_version, 1)
        self.assertEqual(result.signal.expected["parameters"]["unit"], "milliseconds")

    def test_missing_effective_contract_is_not_healthy(self):
        source = snapshot().model_copy(
            update={
                "contracts": (contract(effective_from=NOW - timedelta(seconds=10)),)
            }
        )
        self.assertEqual(self.result(source).status, "missing_contract")

    def test_unsupported_rules_and_invalid_parameters_are_visible(self):
        source = snapshot().model_copy(
            update={"contracts": (contract(kind="null_ratio"),)}
        )
        self.assertEqual(self.result(source).status, "unsupported_rule")
        invalid = contract()
        rule = invalid.rules[0].model_copy(update={"parameters": {"unit": "hours"}})
        source = snapshot().model_copy(
            update={"contracts": (invalid.model_copy(update={"rules": (rule,)}),)}
        )
        self.assertEqual(self.result(source).status, "invalid_contract")

    def test_evidence_limit_does_not_emit_partial_diagnosis(self):
        result = self.result(snapshot("seconds").model_copy(update={"overflow": True}))
        self.assertEqual(result.status, "evidence_limit")
        self.assertIsNone(result.signal)

    def test_contract_boundaries_are_inclusive(self):
        event = sample(NOW)
        bounds = TimestampBounds(unit="milliseconds")
        instant = int(NOW.timestamp() * 1000)
        self.assertTrue(plausible(instant - 60000, event, bounds))
        self.assertTrue(plausible(instant + 5000, event, bounds))
        self.assertFalse(plausible(instant - 60001, event, bounds))
        self.assertFalse(plausible(instant + 5001, event, bounds))


class DetectionWorkerTests(unittest.TestCase):
    def test_worker_runs_detection_and_stops_cleanly(self):
        repository = MagicMock()
        worker = DetectionWorker(repository, "orders")
        repository.evaluate_and_capture.side_effect = lambda *args: worker.stop()
        worker.run()
        repository.initialize.assert_called_once_with("orders")
        repository.evaluate_and_capture.assert_called_once_with("orders", evaluate)
        self.assertEqual(worker.status()["worker"], "stopped")


class DetectionApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = MagicMock()
        app.state.detection_repository = self.repository
        self.addCleanup(lambda: delattr(app.state, "detection_repository"))

    async def test_contract_endpoint_exposes_declarative_definition(self):
        self.repository.contracts.return_value = [
            {"definition": contract().model_dump(mode="json")}
        ]
        status, body = await request(app, "/api/contracts")
        self.assertEqual(status, 200)
        self.assertEqual(body[0]["rules"][0]["kind"], "timestamp_bounds")

    async def test_incident_list_is_bounded(self):
        status, _ = await request(app, "/api/incidents", query=b"limit=101")
        self.assertEqual(status, 422)
        self.repository.incidents.assert_not_called()

    async def test_missing_incident_and_evidence_return_not_found(self):
        self.repository.incident.return_value = None
        self.repository.evidence.return_value = None
        for path in (f"/api/incidents/{uuid4()}", f"/api/incidents/{uuid4()}/evidence"):
            status, _ = await request(app, path)
            self.assertEqual(status, 404)

    async def test_evidence_endpoint_uses_captured_sources(self):
        captured = {
            "snapshot_id": str(uuid4()),
            "body": {"producer_configuration_history": [{"revision": 2}]},
        }
        self.repository.evidence.return_value = captured
        status, body = await request(app, f"/api/incidents/{uuid4()}/evidence")
        self.assertEqual(status, 200)
        self.assertEqual(body, captured)

    async def test_storage_failure_does_not_expose_connection_details(self):
        self.repository.status.side_effect = OperationalError("password=secret")
        status, body = await request(app, "/api/detection")
        self.assertEqual(status, 503)
        self.assertNotIn("secret", str(body))

    async def test_detector_lifecycle_is_independent_of_stream_worker(self):
        with (
            patch.dict(
                os.environ,
                {
                    "STREAM_ENABLED": "false",
                    "DETECTION_ENABLED": "true",
                    "INVESTIGATION_ENABLED": "false",
                },
            ),
            patch("sentinel.main.DetectionWorker") as detector,
        ):
            async with lifespan(app):
                self.assertEqual(app.state.detection_worker, detector.return_value)
            detector.return_value.stop.assert_called_once()
