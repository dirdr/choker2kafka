import asyncio
import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from detection_fixtures import snapshot
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage, RunUsage
from support import request

from sentinel.detection.detectors import evaluate
from sentinel.investigation.agent import investigate
from sentinel.investigation.domain import CapturedEvidence, Finding, UnsupportedFinding
from sentinel.investigation.postgres import InvestigationConflict
from sentinel.investigation.service import InvestigationWorker
from sentinel.main import app


class CountedFunctionModel(FunctionModel):
    async def count_tokens(self, *args, **kwargs):
        return RequestUsage(input_tokens=100)


def evidence():
    source = snapshot("seconds").model_dump(mode="json")
    revision = source["events"][-1]["config_revision"]
    return CapturedEvidence(
        str(uuid4()),
        {
            "snapshot": source,
            "evaluation": evaluate(snapshot("seconds"))[0].model_dump(mode="json"),
            "producer_configuration_history": [
                {
                    "producer_id": "checkout",
                    "revision": revision,
                    "event_time_unit": "seconds",
                }
            ],
            "producer_context_versions": [
                {
                    "producer_id": "checkout",
                    "version": 1,
                    "consumers": [{"consumer_id": "dashboard"}],
                }
            ],
            "missing_configuration_revisions": [],
            "memory_capture_status": "not_implemented",
        },
    )


def finding(source):
    event = source.events[-1]
    return Finding(
        conclusion="supported",
        likely_cause="Producer emits seconds while the contract requires milliseconds",
        alternatives=[
            "Delayed delivery is inconsistent with the recent ingestion timestamps"
        ],
        affected_consumers=["dashboard"],
        recommendation="Review a change back to milliseconds",
        confidence="high",
        confidence_rationale="Captured event revision matches the configuration history",
        evidence_ids=[
            f"event:{event['event_id']}",
            f"configuration:checkout:{event['config_revision']}",
            f"contract:{source.body['snapshot']['contracts'][0]['contract_id']}:1",
        ],
        attribution={
            "producer_id": "checkout",
            "configuration_revision": event["config_revision"],
        },
    )


class EvidenceValidationTests(unittest.TestCase):
    def setUp(self):
        self.source = evidence()
        self.finding = finding(self.source)

    def read_all(self):
        self.source.read("inspect_incident")
        self.source.read("lookup_producer_context")

    def test_unread_evidence_cannot_support_a_finding(self):
        with self.assertRaises(UnsupportedFinding):
            self.source.validate(self.finding)

    def test_valid_attribution_uses_captured_revision_and_consumers(self):
        self.read_all()
        self.assertEqual(self.source.validate(self.finding), self.finding)

    def test_unknown_reference_or_consumer_is_rejected(self):
        self.read_all()
        for update in (
            {"evidence_ids": ["event:invented"]},
            {"affected_consumers": ["invented"]},
        ):
            with self.assertRaises(UnsupportedFinding):
                self.source.validate(self.finding.model_copy(update=update))

    def test_missing_configuration_and_truncated_context_require_abstention(self):
        self.read_all()
        for update in (
            {
                "missing_configuration_revisions": [
                    self.finding.attribution.configuration_revision
                ]
            },
            {"context_history_truncated": True},
        ):
            self.source.body.update(update)
            with self.assertRaises(UnsupportedFinding):
                self.source.validate(self.finding)

    def test_abstention_cannot_include_attribution_or_high_confidence(self):
        self.read_all()
        abstention = self.finding.model_copy(
            update={"conclusion": "insufficient_evidence"}
        )
        with self.assertRaises(UnsupportedFinding):
            self.source.validate(abstention)
        abstention = abstention.model_copy(
            update={"attribution": None, "confidence": "low"}
        )
        self.assertEqual(self.source.validate(abstention), abstention)

    def test_memory_unavailability_is_explicit(self):
        self.assertEqual(
            self.source.read("find_prior_incidents")["status"], "not_implemented"
        )


class InvestigationAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_agent_tool_dispatch_and_typed_output_with_local_model(self):
        source = evidence()
        expected = finding(source)
        calls = []

        def model(messages, info):
            if len(messages) == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart("inspect_incident", {}, "inspect"),
                        ToolCallPart("lookup_producer_context", {}, "context"),
                    ]
                )
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        info.output_tools[0].name,
                        expected.model_dump(mode="json"),
                        "finding",
                    )
                ]
            )

        usage = RunUsage()
        actual = await investigate(
            source,
            lambda *args: calls.append(args),
            usage,
            20000,
            CountedFunctionModel(model),
        )
        self.assertEqual(actual, expected)
        self.assertEqual(
            [c[2] for c in calls], ["started", "returned", "started", "returned"]
        )
        self.assertEqual(usage.tool_calls, 2)
        self.assertEqual(usage.requests, 2)

    async def test_tool_call_limit_stops_a_loop(self):
        source = evidence()
        calls = []

        def model(messages, info):
            return ModelResponse(
                parts=[
                    ToolCallPart("find_prior_incidents", {}, str(i)) for i in range(11)
                ]
            )

        with self.assertRaises(Exception) as caught:
            await investigate(
                source,
                lambda *args: calls.append(args),
                RunUsage(),
                20000,
                CountedFunctionModel(model),
            )
        self.assertEqual(type(caught.exception).__name__, "UsageLimitExceeded")
        self.assertLessEqual(len(calls), 20)

    async def test_token_budget_blocks_inference_before_spending(self):
        class OversizedModel(CountedFunctionModel):
            async def count_tokens(self, *args, **kwargs):
                return RequestUsage(input_tokens=5000)

        model = MagicMock()
        with self.assertRaises(Exception) as caught:
            await investigate(
                evidence(), MagicMock(), RunUsage(), 4000, OversizedModel(model)
            )
        self.assertEqual(type(caught.exception).__name__, "UsageLimitExceeded")
        model.assert_not_called()

    async def test_deadline_cancels_a_stalled_model(self):
        async def model(messages, info):
            await asyncio.sleep(10)
            return ModelResponse(parts=[])

        timeout = asyncio.timeout
        with (
            patch(
                "sentinel.investigation.agent.asyncio.timeout",
                side_effect=lambda seconds: timeout(0.01),
            ),
            self.assertRaises(TimeoutError),
        ):
            await investigate(
                evidence(), MagicMock(), RunUsage(), 20000, CountedFunctionModel(model)
            )


class InvestigationWorkerTests(unittest.TestCase):
    def test_failure_is_saved_without_exception_text_or_automatic_retry(self):
        repository = MagicMock()
        repository.evidence.side_effect = RuntimeError("secret key")
        worker = InvestigationWorker(repository)
        worker.process(
            {"snapshot_id": uuid4(), "investigation_id": uuid4(), "token_limit": 20000}
        )
        args = repository.finish.call_args.args
        self.assertEqual(args[-1], "RuntimeError")
        self.assertNotIn("secret", str(args))
        repository.retry.assert_not_called()


class InvestigationApiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = MagicMock()
        app.state.investigation_repository = self.repository
        self.addCleanup(lambda: delattr(app.state, "investigation_repository"))

    async def test_detail_missing_returns_404(self):
        self.repository.detail.return_value = None
        status, _ = await request(app, f"/api/investigations/{uuid4()}")
        self.assertEqual(status, 404)

    async def test_retry_requires_authentication(self):
        with patch.dict(os.environ, {"OPERATOR_TOKEN": "test"}):
            status, _ = await request(
                app, f"/api/incidents/{uuid4()}/investigations/retry", method="POST"
            )
        self.assertEqual(status, 401)
        self.repository.retry.assert_not_called()

    async def test_retry_rejects_nonfailed_run(self):
        app.state.investigation_worker = MagicMock()
        self.addCleanup(lambda: delattr(app.state, "investigation_worker"))
        self.repository.retry.side_effect = InvestigationConflict()
        with patch.dict(os.environ, {"OPERATOR_TOKEN": "test"}):
            status, _ = await request(
                app,
                f"/api/incidents/{uuid4()}/investigations/retry",
                method="POST",
                token="test",
            )
        self.assertEqual(status, 409)
