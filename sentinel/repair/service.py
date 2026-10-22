import logging
import os
from threading import Event, Lock

from sentinel.github import GitHubClient, GitHubError
from sentinel.repair.domain import RepairBlocked
from sentinel.repair.github import open_pull_request
from sentinel.repair.postgres import RepairRepository
from sentinel.repair.recovery import verify_recovery

logger = logging.getLogger(__name__)


class RepairWorker:
    def __init__(self, repository: RepairRepository):
        self.repository = repository
        self.stopping = Event()
        self.lock = Lock()
        self.state = "starting"
        self.last_error = None
        self.initialized = False

    def status(self) -> dict:
        with self.lock:
            return {"worker": self.state, "last_error": self.last_error}

    def process(self, client: GitHubClient, repair: dict) -> None:
        try:
            if repair["status"] in {"queued", "opening", "error"}:
                if (
                    self.repository.current_revision(repair["proposal"]["producer_id"])
                    != repair["proposal"]["expected_revision"]
                ):
                    raise RepairBlocked("runtime_revision_changed")
                if not self.repository.contract_is_current(repair["proposal"]):
                    raise RepairBlocked("active_contract_changed")
                self.repository.update(repair, "opening")
                pr = open_pull_request(client, repair)
                self.repository.update(repair, "open", pr=pr)
            else:
                pr = client.request("GET", f"/pulls/{repair['pr_number']}")
                if pr.get("merged_at"):
                    if repair["status"] != "merged":
                        self.repository.update(
                            repair, "merged", merge_commit=pr.get("merge_commit_sha")
                        )
                        repair = {**repair, "status": "merged"}
                    result = verify_recovery(self.repository.storage, repair)
                    if result["status"] not in {"verified", "checking"}:
                        self.repository.update(repair, "merged", error=result["status"])
                elif pr["state"] == "closed":
                    self.repository.update(repair, "closed")
        except RepairBlocked as error:
            self.repository.update(repair, "stale", error=str(error))
        except GitHubError as error:
            self.repository.update(
                repair,
                "error" if not repair.get("pr_number") else repair["status"],
                error=f"github_{error.status}",
            )

    def step(self) -> None:
        if not self.initialized:
            self.repository.storage.initialize()
            self.initialized = True
        if not os.getenv("GITHUB_TOKEN"):
            with self.lock:
                self.state, self.last_error = "not_configured", "GITHUB_TOKEN"
            return
        client = GitHubClient()
        self.repository.propose(client)
        for repair in self.repository.pending():
            if self.stopping.is_set():
                break
            self.process(client, repair)
        with self.lock:
            self.state, self.last_error = "running", None

    def run(self) -> None:
        try:
            while not self.stopping.is_set():
                try:
                    self.step()
                except Exception as error:
                    logger.warning("Repair worker failed (%s)", type(error).__name__)
                    with self.lock:
                        self.state, self.last_error = "retrying", type(error).__name__
                self.stopping.wait(5)
        finally:
            with self.lock:
                self.state = "stopped"

    def stop(self) -> None:
        self.stopping.set()
