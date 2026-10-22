import asyncio
import logging
import os
from dataclasses import asdict
from threading import Event, Lock
from time import monotonic

from pydantic_ai.usage import RunUsage

from sentinel.connections import required
from sentinel.investigation.agent import MODEL_ID, investigate, token_limit
from sentinel.investigation.domain import CapturedEvidence, UnsupportedFinding
from sentinel.investigation.postgres import InvestigationRepository

logger = logging.getLogger(__name__)


class InvestigationWorker:
    def __init__(self, repository: InvestigationRepository):
        self.repository = repository
        self.stopping = Event()
        self.lock = Lock()
        self.state = "starting"
        self.last_error = None
        self.initialized = False

    def set_state(self, state: str, error: str | None = None) -> None:
        with self.lock:
            self.state, self.last_error = state, error

    def status(self) -> dict:
        with self.lock:
            return {"worker": self.state, "last_error": self.last_error}

    def process(self, run: dict) -> None:
        started = monotonic()
        usage = RunUsage()
        finding = None
        error_code = None
        try:
            evidence = CapturedEvidence(
                str(run["snapshot_id"]), self.repository.evidence(run["snapshot_id"])
            )
            finding = asyncio.run(
                investigate(
                    evidence,
                    lambda call_id, name, phase, body: self.repository.activity(
                        run["investigation_id"], call_id, name, phase, body
                    ),
                    usage,
                    run["token_limit"],
                    model_id=run["model_id"],
                )
            ).model_dump(mode="json")
        except Exception as error:
            error_code = (
                "unsupported_finding"
                if isinstance(error, UnsupportedFinding)
                else type(error).__name__
            )
            logger.warning("Investigation failed (%s)", error_code)
        self.repository.finish(
            run["investigation_id"],
            finding,
            {k: v for k, v in asdict(usage).items() if isinstance(v, (int, dict))},
            int((monotonic() - started) * 1000),
            error_code,
        )

    def run(self) -> None:
        try:
            while not self.stopping.is_set():
                try:
                    required("ANTHROPIC_API_KEY")
                    budget = token_limit()
                    if not self.initialized:
                        self.repository.storage.initialize()
                        self.initialized = True
                    self.repository.enqueue(
                        MODEL_ID, budget, os.getenv("KAFKA_TOPIC", "orders")
                    )
                    run = self.repository.claim()
                    self.set_state("running")
                    if run:
                        self.process(run)
                    else:
                        self.stopping.wait(2)
                except Exception as error:
                    logger.warning(
                        "Investigation worker failed (%s)", type(error).__name__
                    )
                    self.set_state("retrying", type(error).__name__)
                    self.stopping.wait(5)
        finally:
            self.set_state("stopped")

    def stop(self) -> None:
        self.stopping.set()
