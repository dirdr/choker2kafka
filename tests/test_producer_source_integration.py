import os
import unittest

import test_detection_integration as detection_tests

from sentinel.producer.domain import ProducerFile, SourceFile
from sentinel.producer.postgres import ProducerRepository


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "Set TEST_DATABASE_URL to a dedicated PostgreSQL test database",
)
class ProducerSourceIntegrationTests(unittest.TestCase):
    def setUp(self):
        detection_tests.DetectionIntegrationTests.setUp(self)
        self.producers = ProducerRepository(self.storage)

    def source(self, unit, blob, commit):
        return SourceFile(
            ProducerFile(producer_id="checkout", event_time_unit=unit),
            blob,
            commit,
            "dirdr/choker2kafka",
            "main",
        )

    def test_changed_file_applies_once_and_reverts_create_new_revisions(self):
        first = self.source("milliseconds", "healthy-blob", "healthy-commit")
        self.assertTrue(self.producers.apply(first)["changed"])
        original = self.storage.configuration()
        self.assertFalse(self.producers.apply(first)["changed"])
        self.assertFalse(
            self.producers.apply(
                self.source("milliseconds", "healthy-blob", "unrelated-commit")
            )["changed"]
        )
        self.assertEqual(self.storage.configuration(), original)
        bad = self.source("seconds", "bad-blob", "bad-commit")
        self.assertTrue(self.producers.apply(bad)["changed"])
        faulty = self.storage.configuration()
        self.assertEqual(faulty.revision, original.revision + 1)
        self.assertEqual(faulty.source_commit, "bad-commit")
        history = self.storage.configuration_history()[0]
        self.assertEqual(history["source_file_sha"], "bad-blob")
        self.assertEqual(history["source_commit"], "bad-commit")
        self.assertTrue(self.producers.apply(first)["changed"])
        self.assertEqual(self.storage.configuration().revision, faulty.revision + 1)
        self.assertEqual(
            self.producers.list()[0]["configuration"]["event_time_unit"], "milliseconds"
        )
