import os
import unittest
from unittest.mock import MagicMock, patch

from sentinel.demo.reset import DemoReset
from sentinel.producer.domain import ProducerFile, SourceFile


class DemoResetTests(unittest.TestCase):
    def test_existing_reset_does_not_touch_kafka_or_github(self):
        reset = DemoReset(MagicMock(), MagicMock())
        with (
            patch.object(reset, "applied", return_value=True),
            patch("sentinel.demo.reset.GitHubClient") as github,
        ):
            self.assertEqual(reset.run("already-applied")["status"], "already_applied")
        reset.stream.watermarks.assert_not_called()
        github.assert_not_called()

    def test_faulty_desired_configuration_blocks_deletion(self):
        reset = DemoReset(MagicMock(), MagicMock())
        source = SourceFile(
            ProducerFile(producer_id="checkout", event_time_unit="seconds"),
            "bad",
            "commit",
            "repo/name",
            "main",
        )
        with (
            patch.dict(os.environ, {"GITHUB_TOKEN": "test"}),
            patch.object(reset, "applied", return_value=False),
            patch("sentinel.demo.reset.GitHubClient"),
            patch("sentinel.demo.reset.SourceFile.github", return_value=source),
            patch.object(reset, "clear") as clear,
            self.assertRaisesRegex(ValueError, "healthy producer"),
        ):
            reset.run("new-reset")
        clear.assert_not_called()
        reset.stream.watermarks.assert_not_called()
