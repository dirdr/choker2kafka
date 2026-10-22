import logging
from collections.abc import Callable
from threading import Event, Lock
from typing import Protocol

from sentinel.detection.detectors import evaluate
from sentinel.detection.domain import CheckResult, WindowSnapshot

logger = logging.getLogger(__name__)


class DetectionStore(Protocol):
    def initialize(self, topic: str) -> None: ...

    def evaluate_and_capture(
        self, topic: str, detector: Callable[[WindowSnapshot], list[CheckResult]]
    ) -> list[CheckResult]: ...


class DetectionWorker:
    def __init__(self, repository: DetectionStore, topic: str):
        self.repository = repository
        self.topic = topic
        self.stopping = Event()
        self.lock = Lock()
        self.state = "starting"
        self.last_error = None

    def set_state(self, state: str, error: str | None = None) -> None:
        with self.lock:
            self.state, self.last_error = state, error

    def status(self) -> dict:
        with self.lock:
            return {"worker": self.state, "last_error": self.last_error}

    def run(self) -> None:
        try:
            while not self.stopping.is_set():
                try:
                    self.repository.initialize(self.topic)
                    self.set_state("running")
                    while not self.stopping.is_set():
                        self.repository.evaluate_and_capture(self.topic, evaluate)
                        self.stopping.wait(5)
                except Exception as error:
                    logger.warning("Detection worker failed (%s)", type(error).__name__)
                    self.set_state("retrying", type(error).__name__)
                self.stopping.wait(5)
        finally:
            self.set_state("stopped")

    def stop(self) -> None:
        self.stopping.set()
