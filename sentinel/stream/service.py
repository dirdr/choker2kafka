import logging
from threading import Event, Lock
from time import monotonic

from sentinel.stream.domain import make_order
from sentinel.stream.ports import EventRepository, EventStream

logger = logging.getLogger(__name__)


class StreamWorker:
    def __init__(
        self, repository: EventRepository, stream: EventStream, code_version: str
    ):
        self.repository = repository
        self.stream = stream
        self.code_version = code_version
        self.stopping = Event()
        self.lock = Lock()
        self.state = "starting"
        self.last_error = None
        self.next_batch_at = 0.0

    def status(self) -> dict:
        with self.lock:
            return {"worker": self.state, "last_error": self.last_error}

    def set_state(self, state: str, error: str | None = None) -> None:
        with self.lock:
            self.state = state
            self.last_error = error

    def step(self) -> None:
        now = monotonic()
        if now >= self.next_batch_at:
            configuration = self.repository.configuration()
            self.stream.publish(
                [
                    make_order(
                        configuration, configuration.source_commit or self.code_version
                    )
                    for _ in range(10)
                ]
            )
            self.next_batch_at = now + 1
        records = self.stream.receive()
        if records:
            self.repository.store(records)
            self.stream.acknowledge(records)

    def run(self) -> None:
        try:
            while not self.stopping.is_set():
                try:
                    self.set_state("starting")
                    self.repository.initialize()
                    self.stream.open()
                    self.next_batch_at = 0
                    self.set_state("running")
                    while not self.stopping.is_set():
                        self.step()
                        self.stopping.wait(0.05)
                except Exception as error:
                    logger.warning("Stream worker failed (%s)", type(error).__name__)
                    self.set_state("retrying", type(error).__name__)
                finally:
                    try:
                        self.stream.close()
                    except Exception as error:
                        logger.warning("Stream close failed (%s)", type(error).__name__)
                self.stopping.wait(5)
        finally:
            self.set_state("stopped")

    def stop(self) -> None:
        self.stopping.set()
