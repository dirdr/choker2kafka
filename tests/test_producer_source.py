import base64
import os
import unittest
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

from sentinel.github import GitHubClient
from sentinel.producer.domain import ProducerFile, SourceFile
from sentinel.producer.service import ProducerSourceWorker


class ProducerSourceTests(unittest.TestCase):
    def test_config_is_restricted_to_supported_fields(self):
        for config in (
            {"producer_id": "checkout", "event_time_unit": "minutes"},
            {"producer_id": "other", "event_time_unit": "seconds"},
            {"producer_id": "checkout", "event_time_unit": "seconds", "command": "run"},
        ):
            with self.assertRaises(ValidationError):
                ProducerFile.model_validate(config)

    def test_github_source_preserves_blob_and_commit_provenance(self):
        config = ProducerFile(producer_id="checkout", event_time_unit="seconds")
        source = SourceFile.github(
            {
                "type": "file",
                "path": "producer/config.json",
                "size": 100,
                "content": base64.b64encode(config.contents()).decode(),
                "sha": "blob",
            },
            "commit",
            "dirdr/choker2kafka",
            "main",
        )
        self.assertEqual(source.configuration, config)
        self.assertEqual(source.file_sha, "blob")
        self.assertEqual(source.commit_sha, "commit")

    def test_github_source_rejects_other_paths(self):
        with self.assertRaises(ValueError):
            SourceFile.github(
                {"type": "file", "path": "other.json"}, "commit", "repo/name", "main"
            )

    def test_worker_reads_one_consistent_commit(self):
        repository = MagicMock()
        config = ProducerFile(producer_id="checkout", event_time_unit="seconds")
        with (
            patch.dict(os.environ, {"GITHUB_TOKEN": "test"}),
            patch("sentinel.producer.service.GitHubClient") as github,
        ):
            github.return_value.head.return_value = "commit"
            github.return_value.repository = "dirdr/choker2kafka"
            github.return_value.branch = "main"
            github.return_value.file.return_value = {
                "type": "file",
                "path": "producer/config.json",
                "size": 100,
                "content": base64.b64encode(config.contents()).decode(),
                "sha": "blob",
            }
            worker = ProducerSourceWorker(repository)
            worker.step()
        github.return_value.file.assert_called_once_with("commit")
        self.assertEqual(repository.apply.call_args.args[0].commit_sha, "commit")
        self.assertEqual(worker.status()["worker"], "watching")

    def test_repository_validation_prevents_url_injection(self):
        with (
            patch.dict(os.environ, {"GITHUB_REPOSITORY": "https://outside.test"}),
            self.assertRaises(ValueError),
        ):
            GitHubClient()
