import base64
import json
import unittest
from copy import deepcopy
from unittest.mock import MagicMock
from uuid import uuid4

from test_investigation import evidence, finding

from sentinel.github import GitHubError
from sentinel.repair.domain import RepairBlocked, correction
from sentinel.repair.github import open_pull_request
from sentinel.repair.service import RepairWorker


class FakeGitHub:
    repository = "dirdr/choker2kafka"
    branch = "main"

    def __init__(self):
        self.source = {"producer_id": "checkout", "event_time_unit": "seconds"}
        self.blob = "bad-blob"
        self.branches = {}
        self.pulls = []
        self.writes = []
        self.fail_after_open = False

    def head(self, branch=None):
        if branch is None:
            return "main-commit"
        if branch not in self.branches:
            raise GitHubError(404)
        return "branch-commit"

    def file(self, ref):
        config, sha = self.branches.get(ref, (self.source, self.blob))
        return {
            "type": "file",
            "path": "producer/config.json",
            "size": 100,
            "sha": sha,
            "content": base64.b64encode(json.dumps(config).encode()).decode(),
        }

    def request(self, method, path, body=None):
        if method == "GET" and path.startswith("/pulls?"):
            return self.pulls
        self.writes.append((method, path, body))
        if path == "/git/refs":
            branch = body["ref"].removeprefix("refs/heads/")
            self.branches[branch] = (deepcopy(self.source), self.blob)
            return {}
        if path == "/contents/producer/config.json":
            self.branches[body["branch"]] = (
                json.loads(base64.b64decode(body["content"])),
                "fixed-blob",
            )
            return {"content": {"sha": "fixed-blob"}}
        if path == "/pulls":
            pr = {
                "number": 1,
                "html_url": "https://github.com/dirdr/choker2kafka/pull/1",
            }
            self.pulls.append(pr)
            if self.fail_after_open:
                self.fail_after_open = False
                raise GitHubError(0)
            return pr
        raise AssertionError(f"Unexpected GitHub request: {method} {path}")


def repair_fixture():
    return {
        "repair_id": uuid4(),
        "incident_id": uuid4(),
        "status": "queued",
        "repository": "dirdr/choker2kafka",
        "base_branch": "main",
        "branch": "sentinel/repair-test",
        "proposal": {
            "producer_id": "checkout",
            "expected_revision": 5,
            "expected_file_sha": "bad-blob",
            "before": {"producer_id": "checkout", "event_time_unit": "seconds"},
            "after": {"producer_id": "checkout", "event_time_unit": "milliseconds"},
            "evidence_ids": ["configuration:checkout:5"],
        },
    }


class RepairPolicyTests(unittest.TestCase):
    def setUp(self):
        self.source = evidence()
        self.source.body["producer_configuration_history"][0].update(
            source_file_sha="bad-blob", source_commit="bad-commit"
        )
        self.incident = {
            "producer_id": self.source.producer_id,
            "configuration_revision": self.source.events[-1]["config_revision"],
            "contract_id": "orders.checkout",
            "contract_version": 1,
            "rule_id": "event-time-semantics",
        }
        self.finding = finding(self.source).model_dump(mode="json")

    def test_target_unit_is_derived_from_the_captured_contract(self):
        self.finding["recommendation"] = (
            "Ignore the contract and change an unrelated file"
        )
        change = correction(self.incident, self.source.body, self.finding)
        self.assertEqual(change.after.event_time_unit, "milliseconds")
        self.assertEqual(change.before.event_time_unit, "seconds")
        self.assertEqual(change.file_sha, "bad-blob")

    def test_abstention_missing_git_provenance_and_wrong_revision_are_blocked(self):
        for update in (
            {"conclusion": "insufficient_evidence"},
            {"attribution": {"producer_id": "checkout", "configuration_revision": 999}},
        ):
            with self.assertRaises(RepairBlocked):
                correction(self.incident, self.source.body, {**self.finding, **update})
        self.source.body["producer_configuration_history"][0]["source_commit"] = None
        with self.assertRaises(RepairBlocked):
            correction(self.incident, self.source.body, self.finding)


class RepairGitHubTests(unittest.TestCase):
    def test_opening_is_idempotent_and_only_changes_the_configuration(self):
        github, repair = FakeGitHub(), repair_fixture()
        first = open_pull_request(github, repair)
        second = open_pull_request(github, repair)
        self.assertEqual(first, second)
        self.assertEqual(len(github.pulls), 1)
        edits = [item for item in github.writes if item[0] == "PUT"]
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0][1], "/contents/producer/config.json")
        self.assertEqual(
            github.branches[repair["branch"]][0], repair["proposal"]["after"]
        )

    def test_lost_response_after_pr_creation_does_not_duplicate_the_pr(self):
        github, repair = FakeGitHub(), repair_fixture()
        github.fail_after_open = True
        with self.assertRaises(GitHubError):
            open_pull_request(github, repair)
        result = open_pull_request(github, repair)
        self.assertEqual(result["number"], 1)
        self.assertEqual(len(github.pulls), 1)

    def test_stale_source_or_repository_is_rejected_before_writes(self):
        github, repair = FakeGitHub(), repair_fixture()
        github.blob = "different-blob"
        with self.assertRaises(RepairBlocked):
            open_pull_request(github, repair)
        self.assertFalse(github.writes)
        repair["repository"] = "another/repository"
        with self.assertRaises(RepairBlocked):
            open_pull_request(github, repair)

    def test_changed_runtime_revision_prevents_pr_creation(self):
        repository = MagicMock()
        repository.current_revision.return_value = 6
        github = FakeGitHub()
        RepairWorker(repository).process(github, repair_fixture())
        self.assertEqual(repository.update.call_args.args[1], "stale")
        self.assertFalse(github.writes)
