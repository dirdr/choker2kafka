import asyncio
import json
import os
import threading
import unittest
from contextlib import ExitStack
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import psycopg
from confluent_kafka import KafkaError, KafkaException

from sentinel import readiness
from sentinel.main import app


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_missing_configuration(self):
        for probe in (
            readiness.check_postgres,
            readiness.check_kafka,
            readiness.check_anthropic,
        ):
            with self.subTest(probe=probe.__name__):
                self.assertEqual(probe()["status"], "not_configured")

    def test_postgres_executes_query_and_requires_tls(self):
        os.environ["DATABASE_URL"] = "postgresql://user:secret@localhost/db"
        with patch.object(readiness.psycopg, "connect") as connect:
            cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (True,)
            self.assertEqual(readiness.check_postgres(), {"status": "ok"})
            self.assertEqual(connect.call_args.kwargs["sslmode"], "require")
            cursor.execute.assert_called_once_with(
                "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"
            )
            cursor.fetchone.return_value = (False,)
            self.assertEqual(readiness.check_postgres()["status"], "error")

    def test_postgres_rejects_insecure_and_malformed_configuration(self):
        with patch.object(readiness.psycopg, "connect") as connect:
            for url in (
                "postgresql://user:secret@localhost/db?sslmode=disable",
                "invalid-connection-string",
            ):
                with self.subTest(url=url):
                    os.environ["DATABASE_URL"] = url
                    self.assertEqual(readiness.check_postgres()["status"], "error")
            connect.assert_not_called()

    def test_postgres_failure_does_not_expose_credentials(self):
        os.environ["DATABASE_URL"] = "postgresql://user:secret@localhost/db"
        with patch.object(
            readiness.psycopg, "connect", side_effect=psycopg.OperationalError("secret")
        ):
            result = readiness.check_postgres()
        self.assertEqual(result["status"], "error")
        self.assertNotIn("secret", json.dumps(result))

    def configure_kafka(self):
        os.environ.update(
            KAFKA_BOOTSTRAP_SERVERS="localhost:9093",
            KAFKA_CA_CERT="certificate\\ncontent",
            KAFKA_SASL_USERNAME="user",
            KAFKA_SASL_PASSWORD="secret",
        )

    def test_kafka_authentication_and_metadata(self):
        self.configure_kafka()
        with patch.object(readiness, "AdminClient") as client:
            client.return_value.list_topics.return_value = SimpleNamespace(
                brokers={1: object()}
            )
            self.assertEqual(readiness.check_kafka(), {"status": "ok"})
            client.return_value.list_topics.assert_called_once_with(timeout=5)
            self.assertEqual(client.call_args.args[0]["security.protocol"], "SASL_SSL")
            self.assertEqual(
                client.call_args.args[0]["ssl.ca.pem"], "certificate\ncontent"
            )
            client.return_value.list_topics.return_value.brokers = {}
            self.assertEqual(readiness.check_kafka()["status"], "error")

    def test_kafka_supports_mutual_tls(self):
        self.configure_kafka()
        os.environ.update(
            KAFKA_SECURITY_PROTOCOL="SSL",
            KAFKA_ACCESS_CERT="client\\ncertificate",
            KAFKA_ACCESS_KEY="client\\nkey",
        )
        config = readiness.kafka_configuration()
        self.assertEqual(config["ssl.key.pem"], "client\nkey")
        self.assertNotIn("sasl.password", config)

    def test_kafka_reads_ca_value_without_accessing_certificate_files(self):
        self.configure_kafka()
        pem = "-----BEGIN CERTIFICATE-----\ncertificate-content\n-----END CERTIFICATE-----"
        os.environ["KAFKA_SSL_CA_LOCATION"] = "missing-runtime-file.pem"
        for value in (pem, pem.replace("\n", "\\n"), f"\n{pem}\n"):
            with self.subTest(value=value):
                os.environ["KAFKA_CA_CERT"] = value
                with patch.object(
                    readiness.Path,
                    "is_file",
                    side_effect=AssertionError("File access is not required"),
                ):
                    config = readiness.kafka_configuration()
                self.assertEqual(config["ssl.ca.pem"], pem)
                self.assertNotIn("ssl.ca.location", config)

    def test_kafka_accepts_flattened_and_escaped_environment_certificates(self):
        self.configure_kafka()
        pem = "-----BEGIN CERTIFICATE-----\nYWJjZGVm\n-----END CERTIFICATE-----"
        for value in (
            pem,
            pem.replace("\n", " "),
            pem.replace("\n", "\\n"),
            pem.replace("\n", "\\r\\n"),
            pem.replace("\n", "\r\n"),
            f'"{pem}"',
        ):
            with self.subTest(value=value):
                os.environ["KAFKA_CA_CERT"] = value
                self.assertEqual(readiness.kafka_configuration()["ssl.ca.pem"], pem)

    def test_pem_normalization_preserves_certificate_chains(self):
        first = "-----BEGIN CERTIFICATE----- YWJjZA== -----END CERTIFICATE-----"
        second = "-----BEGIN CERTIFICATE----- ZWZnaA== -----END CERTIFICATE-----"
        result = readiness.normalize_pem(f"{first}\n{second}")
        self.assertEqual(result.count("-----BEGIN CERTIFICATE-----"), 2)
        self.assertIn("\nYWJjZA==\n", result)
        self.assertIn("\nZWZnaA==\n", result)

    def test_kafka_passes_environment_certificate_to_client(self):
        self.configure_kafka()
        os.environ.pop("KAFKA_SSL_CA_LOCATION", None)
        with patch.object(readiness, "AdminClient") as client:
            client.return_value.list_topics.return_value = SimpleNamespace(
                brokers={1: object()}
            )
            self.assertEqual(readiness.check_kafka()["status"], "ok")
        self.assertEqual(client.call_args.args[0]["ssl.ca.pem"], "certificate\ncontent")
        self.assertNotIn("ssl.ca.location", client.call_args.args[0])

    def test_kafka_rejects_insecure_transport_and_missing_ca(self):
        self.configure_kafka()
        os.environ["KAFKA_SECURITY_PROTOCOL"] = "PLAINTEXT"
        self.assertEqual(readiness.check_kafka()["status"], "not_configured")
        del os.environ["KAFKA_SECURITY_PROTOCOL"]
        del os.environ["KAFKA_CA_CERT"]
        os.environ["KAFKA_SSL_CA_LOCATION"] = "missing-ca.pem"
        self.assertEqual(readiness.check_kafka()["status"], "not_configured")

    def test_kafka_failure_does_not_expose_credentials(self):
        self.configure_kafka()
        with patch.object(readiness, "AdminClient", side_effect=ValueError("secret")):
            result = readiness.check_kafka()
        self.assertEqual(result["status"], "error")
        self.assertNotIn("secret", json.dumps(result))

    def test_kafka_reports_safe_failure_categories(self):
        self.configure_kafka()
        for error_code, expected in (
            (KafkaError._SSL, "tls_failed"),
            (KafkaError._AUTHENTICATION, "authentication_failed"),
            (KafkaError.SASL_AUTHENTICATION_FAILED, "authentication_failed"),
            (KafkaError._RESOLVE, "dns_failed"),
            (KafkaError._INVALID_ARG, "invalid_configuration"),
            (KafkaError._TRANSPORT, "connection_failed"),
        ):
            with self.subTest(error_code=error_code):
                error = KafkaException(KafkaError(error_code, "secret"))
                with patch.object(readiness, "AdminClient", side_effect=error):
                    result = readiness.check_kafka()
                self.assertEqual(result["code"], expected)
                self.assertNotIn("secret", json.dumps(result))

    def test_kafka_uses_underlying_failure_when_metadata_times_out(self):
        self.configure_kafka()
        with patch.object(readiness, "AdminClient") as client:
            client.return_value.list_topics.side_effect = KafkaException(
                KafkaError(KafkaError._TRANSPORT)
            )

            def deliver_error(timeout):
                callback = client.call_args.args[0]["error_cb"]
                callback(KafkaError(KafkaError._AUTHENTICATION, "secret"))

            client.return_value.poll.side_effect = deliver_error
            result = readiness.check_kafka()
        self.assertEqual(result["code"], "authentication_failed")
        self.assertNotIn("secret", json.dumps(result))

    def test_anthropic_authenticates_without_generating_tokens(self):
        os.environ["ANTHROPIC_API_KEY"] = "secret"
        with patch.object(readiness, "build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.status = 200
            self.assertEqual(readiness.check_anthropic(), {"status": "ok"})
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(
                request.full_url, "https://api.anthropic.com/v1/models?limit=1"
            )
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.get_header("X-api-key"), "secret")
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 5)

    def test_anthropic_failures_are_safe(self):
        os.environ["ANTHROPIC_API_KEY"] = "secret"
        for error in (
            HTTPError(
                "https://api.anthropic.com", code, "secret", {}, BytesIO(b"secret")
            )
            for code in (401, 403, 429, 500, 302)
        ):
            with self.subTest(code=error.code):
                with patch.object(readiness, "build_opener") as opener:
                    opener.return_value.open.side_effect = error
                    result = readiness.check_anthropic()
                self.assertEqual(result["status"], "error")
                self.assertNotIn("secret", json.dumps(result))
        with patch.object(readiness, "build_opener") as opener:
            opener.return_value.open.side_effect = URLError("secret")
            self.assertEqual(readiness.check_anthropic()["status"], "error")

    def test_anthropic_does_not_forward_key_on_redirect(self):
        self.assertIsNone(
            readiness.NoRedirects().redirect_request(
                None, None, 302, "", {}, "https://elsewhere.test"
            )
        )


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, path):
        messages = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            messages.append(message)

        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [],
                "server": ("test", 80),
                "client": ("test", 1),
                "root_path": "",
            },
            receive,
            send,
        )
        return messages[0], json.loads(messages[1]["body"])

    async def test_readiness_requires_every_dependency(self):
        for failing in (None, "postgres", "kafka", "anthropic"):
            with self.subTest(failing=failing), ExitStack() as stack:
                for name in ("postgres", "kafka", "anthropic"):
                    stack.enter_context(
                        patch.object(
                            readiness,
                            f"check_{name}",
                            return_value={
                                "status": "error" if name == failing else "ok"
                            },
                        )
                    )
                response, body = await self.request("/ready")
                self.assertEqual(response["status"], 503 if failing else 200)
                self.assertEqual(body["status"], "not_ready" if failing else "ready")
                self.assertEqual(
                    set(body["checks"]), {"postgres", "kafka", "anthropic"}
                )
                self.assertIn((b"cache-control", b"no-store"), response["headers"])

    async def test_liveness_does_not_call_dependencies(self):
        with patch.object(readiness, "check_postgres") as probe:
            response, body = await self.request("/health")
        self.assertEqual(response["status"], 200)
        self.assertEqual(body, {"status": "ok"})
        probe.assert_not_called()

    async def test_probes_run_concurrently_off_the_event_loop(self):
        loop = asyncio.get_running_loop()
        started = [asyncio.Event() for _ in range(3)]
        release = threading.Event()

        def probe(index):
            loop.call_soon_threadsafe(started[index].set)
            if not release.wait(timeout=3):
                raise TimeoutError("Probes did not overlap")
            return {"status": "ok"}

        with ExitStack() as stack:
            for index, name in enumerate(("postgres", "kafka", "anthropic")):
                stack.enter_context(
                    patch.object(
                        readiness, f"check_{name}", side_effect=lambda i=index: probe(i)
                    )
                )
            task = asyncio.create_task(self.request("/ready"))
            try:
                await asyncio.wait_for(
                    asyncio.gather(*(event.wait() for event in started)), timeout=2
                )
            finally:
                release.set()
            response, _ = await task
        self.assertEqual(response["status"], 200)
