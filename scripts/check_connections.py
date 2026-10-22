import logging
import os
from pathlib import Path

import psycopg
from confluent_kafka.admin import AdminClient
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def safe_error(error: Exception) -> str:
    message = str(error)
    for key, value in os.environ.items():
        if value and ("PASSWORD" in key or "API_KEY" in key or key == "DATABASE_URL"):
            message = message.replace(value, "[redacted]")
    return message


def check_postgres() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
            row = cursor.fetchone()
            if not row or not row[0]:
                raise RuntimeError("PostgreSQL connection is not using TLS")
    print("PostgreSQL: authenticated; TLS enabled; read-only check passed.")


def check_kafka() -> None:
    ca_path = Path(os.environ["KAFKA_SSL_CA_LOCATION"])
    if not ca_path.is_absolute():
        ca_path = ROOT / ca_path
    logger = logging.getLogger("kafka-connectivity")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    client = AdminClient(
        {
            "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            "security.protocol": os.environ["KAFKA_SECURITY_PROTOCOL"],
            "sasl.mechanism": os.environ["KAFKA_SASL_MECHANISM"],
            "sasl.username": os.environ["KAFKA_SASL_USERNAME"],
            "sasl.password": os.environ["KAFKA_SASL_PASSWORD"],
            "ssl.ca.location": str(ca_path),
            "socket.timeout.ms": 10000,
            "log_level": 0,
        },
        logger=logger,
    )
    metadata = client.list_topics(timeout=12)
    topic = os.environ.get("KAFKA_TOPIC", "orders")
    existing = metadata.topics.get(topic)
    if existing is not None and existing.error is not None:
        raise RuntimeError(f"Topic metadata error: {existing.error}")
    print("Kafka: authenticated; TLS certificate verified; metadata read passed.")
    status = "exists" if existing is not None else "not present; no topic created"
    print(f"Topic {topic!r}: {status}.")


def main() -> int:
    failed = False
    for label, check in (("PostgreSQL", check_postgres), ("Kafka", check_kafka)):
        try:
            check()
        except Exception as error:
            failed = True
            print(f"{label}: FAILED: {safe_error(error)}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
