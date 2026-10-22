import logging
import os
from pathlib import Path
from threading import Event, Lock

from sentinel.github import GitHubClient
from sentinel.producer.domain import CONFIG_PATH, SourceFile
from sentinel.producer.postgres import ProducerRepository

logger = logging.getLogger(__name__)


class ProducerSourceWorker:
    def __init__(self, repository: ProducerRepository):
        self.repository = repository
        self.stopping = Event()
        self.lock = Lock()
        self.state = "starting"
        self.last_error = None
        self.initialized = False
        self.local_applied = False

    def status(self) -> dict:
        with self.lock:
            return {"worker": self.state, "last_error": self.last_error}

    def step(self) -> None:
        if not self.initialized:
            self.repository.storage.initialize()
            self.initialized = True
        if os.getenv("GITHUB_TOKEN"):
            github = GitHubClient()
            commit = github.head()
            source = SourceFile.github(
                github.file(commit), commit, github.repository, github.branch
            )
            self.repository.apply(source)
            state = "watching"
        else:
            if not self.local_applied:
                self.repository.apply(
                    SourceFile.local(
                        (Path(__file__).resolve().parents[2] / CONFIG_PATH).read_bytes()
                    )
                )
                self.local_applied = True
            state = "local_file"
        with self.lock:
            self.state, self.last_error = state, None

    def run(self) -> None:
        try:
            while not self.stopping.is_set():
                try:
                    self.step()
                except Exception as error:
                    logger.warning(
                        "Producer source sync failed (%s)", type(error).__name__
                    )
                    with self.lock:
                        self.state, self.last_error = "retrying", type(error).__name__
                self.stopping.wait(10)
        finally:
            with self.lock:
                self.state = "stopped"

    def stop(self) -> None:
        self.stopping.set()
