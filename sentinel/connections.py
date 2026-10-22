import os
import re
from pathlib import Path
from textwrap import wrap

ROOT = Path(__file__).resolve().parents[1]


class MissingConfiguration(ValueError):
    pass


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MissingConfiguration(name)
    return value


def normalize_pem(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        value = value[1:-1].strip()
    value = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n")

    def format_block(match: re.Match[str]) -> str:
        label, body = match.groups()
        encoded = "".join(body.split())
        return (
            f"-----BEGIN {label}-----\n"
            + "\n".join(wrap(encoded, 64))
            + f"\n-----END {label}-----"
        )

    return re.sub(
        r"-----BEGIN ([A-Z0-9 ]+)-----([A-Za-z0-9+/=\s]+)-----END \1-----",
        format_block,
        value,
    )


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
    if certificate := os.getenv("KAFKA_CA_CERT", "").strip():
        config["ssl.ca.pem"] = normalize_pem(certificate)
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
        config["ssl.certificate.pem"] = normalize_pem(required("KAFKA_ACCESS_CERT"))
        config["ssl.key.pem"] = normalize_pem(required("KAFKA_ACCESS_KEY"))
    return config
