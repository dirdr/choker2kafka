import asyncio
import logging
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

import psycopg
from confluent_kafka import KafkaError, KafkaException
from confluent_kafka.admin import AdminClient
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from psycopg.conninfo import conninfo_to_dict

router = APIRouter()
logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


class MissingConfiguration(ValueError):
    pass


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MissingConfiguration(name)
    return value


def kafka_configuration() -> dict[str, str | int]:
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS") or required(
        "KAFKA_BOOTSTRAP_SERVER"
    )
    protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
    if protocol not in {"SSL", "SASL_SSL"}:
        raise MissingConfiguration("KAFKA_SECURITY_PROTOCOL must be SSL or SASL_SSL")
    config: dict[str, str | int] = {
        "bootstrap.servers": bootstrap,
        "security.protocol": protocol,
        "socket.timeout.ms": 5000,
        "log_level": 0,
    }
    if certificate := os.getenv("KAFKA_CA_CERT"):
        config["ssl.ca.pem"] = certificate.replace("\\n", "\n")
    elif location := os.getenv("KAFKA_SSL_CA_LOCATION"):
        path = Path(location)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            raise MissingConfiguration(
                "KAFKA_SSL_CA_LOCATION must point to an existing file"
            )
        config["ssl.ca.location"] = str(path)
    else:
        raise MissingConfiguration("KAFKA_CA_CERT or KAFKA_SSL_CA_LOCATION")
    if protocol == "SASL_SSL":
        config["sasl.mechanism"] = os.getenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-256")
        config["sasl.username"] = required("KAFKA_SASL_USERNAME")
        config["sasl.password"] = required("KAFKA_SASL_PASSWORD")
    else:
        config["ssl.certificate.pem"] = required("KAFKA_ACCESS_CERT").replace(
            "\\n", "\n"
        )
        config["ssl.key.pem"] = required("KAFKA_ACCESS_KEY").replace("\\n", "\n")
    return config


def check_postgres() -> dict[str, str]:
    try:
        url = required("DATABASE_URL")
        sslmode = conninfo_to_dict(url).get("sslmode", "require")
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            return {"status": "error", "detail": "DATABASE_URL must require TLS"}
        with (
            psycopg.connect(
                url,
                sslmode=sslmode,
                connect_timeout=5,
                options="-c statement_timeout=5000",
                autocommit=True,
            ) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
            row = cursor.fetchone()
            if not row or not row[0]:
                return {"status": "error", "detail": "PostgreSQL TLS is not active"}
        return {"status": "ok"}
    except MissingConfiguration as error:
        return {"status": "not_configured", "detail": str(error)}
    except (psycopg.Error, OSError, ValueError) as error:
        logger.warning("PostgreSQL readiness failed (%s)", type(error).__name__)
        return {
            "status": "error",
            "detail": "Check PostgreSQL credentials, TLS and network access",
        }


def check_kafka() -> dict[str, str]:
    failures: list[int] = []
    client = None
    try:
        client = AdminClient(
            {
                **kafka_configuration(),
                "error_cb": lambda error: failures.append(error.code()),
            }
        )
        metadata = client.list_topics(timeout=5)
        if not metadata.brokers:
            return {"status": "error", "detail": "Kafka returned no brokers"}
        return {"status": "ok"}
    except MissingConfiguration as error:
        return {"status": "not_configured", "detail": str(error)}
    except (KafkaException, RuntimeError, ValueError, OSError) as error:
        if client is not None:
            client.poll(0)
        if (
            isinstance(error, KafkaException)
            and error.args
            and isinstance(error.args[0], KafkaError)
        ):
            failures.append(error.args[0].code())
        logger.warning("Kafka readiness failed (%s)", type(error).__name__)
        if KafkaError._SSL in failures:
            code = "tls_failed"
            detail = "Kafka TLS failed; check the CA certificate and the port for the selected authentication method"
        elif any(
            code in failures
            for code in (
                KafkaError._AUTHENTICATION,
                KafkaError.SASL_AUTHENTICATION_FAILED,
            )
        ):
            code = "authentication_failed"
            detail = "Kafka authentication failed; check the SASL username, password, mechanism and port"
        elif KafkaError._RESOLVE in failures:
            code = "dns_failed"
            detail = (
                "Kafka hostname could not be resolved; check KAFKA_BOOTSTRAP_SERVERS"
            )
        elif KafkaError._INVALID_ARG in failures:
            code = "invalid_configuration"
            detail = "Kafka client configuration is invalid; check the PEM certificate format and authentication settings"
        else:
            code = "connection_failed"
            detail = "Kafka connection failed; check the broker port, network access and authentication method"
        return {
            "status": "error",
            "code": code,
            "detail": detail,
        }


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_anthropic() -> dict[str, str]:
    try:
        key = required("ANTHROPIC_API_KEY")
        request = Request(
            "https://api.anthropic.com/v1/models?limit=1",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        )
        with build_opener(NoRedirects()).open(request, timeout=5) as response:
            if response.status != 200:
                return {
                    "status": "error",
                    "detail": "Anthropic returned an unexpected response",
                }
        return {"status": "ok"}
    except MissingConfiguration as error:
        return {"status": "not_configured", "detail": str(error)}
    except HTTPError as error:
        if error.code in {401, 403}:
            detail = "Anthropic rejected the API key or its permissions"
        elif error.code == 429:
            detail = "Anthropic rate limit reached"
        else:
            detail = "Anthropic API is unavailable"
        error.close()
        return {"status": "error", "detail": detail}
    except (URLError, OSError, ValueError) as error:
        logger.warning("Anthropic readiness failed (%s)", type(error).__name__)
        return {
            "status": "error",
            "detail": "Check Anthropic API connectivity and configuration",
        }


@router.get("/ready", tags=["health"])
async def ready() -> JSONResponse:
    probes = {
        "postgres": check_postgres,
        "kafka": check_kafka,
        "anthropic": check_anthropic,
    }
    results = await asyncio.gather(
        *(asyncio.to_thread(probe) for probe in probes.values())
    )
    checks = dict(zip(probes, results, strict=True))
    available = all(check["status"] == "ok" for check in checks.values())
    return JSONResponse(
        status_code=200 if available else 503,
        content={"status": "ready" if available else "not_ready", "checks": checks},
        headers={"Cache-Control": "no-store"},
    )
