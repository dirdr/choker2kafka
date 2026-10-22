from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from time import time_ns
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class TimestampUnit(StrEnum):
    MILLISECONDS = "milliseconds"
    SECONDS = "seconds"
    MICROSECONDS = "microseconds"


class ProducerConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    producer_id: str = "checkout"
    revision: int = Field(ge=1, le=2**63 - 1, strict=True)
    event_time_unit: TimestampUnit
    source_commit: str | None = None


class ConfigurationChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1, le=2**63 - 1, strict=True)
    event_time_unit: TimestampUnit
    reason: str = Field(min_length=1, max_length=500)


class OrderEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID
    producer_id: str = Field(min_length=1, max_length=100)
    code_version: str = Field(min_length=1, max_length=100)
    config_revision: int = Field(ge=1, le=2**63 - 1, strict=True)
    event_time: int = Field(ge=-(2**63), le=2**63 - 1, strict=True)
    order_id: UUID
    amount_cents: int = Field(ge=1, strict=True)


def make_order(
    configuration: ProducerConfiguration,
    code_version: str,
    now_ns: int | None = None,
) -> OrderEvent:
    divisor = {
        TimestampUnit.SECONDS: 1_000_000_000,
        TimestampUnit.MILLISECONDS: 1_000_000,
        TimestampUnit.MICROSECONDS: 1_000,
    }[configuration.event_time_unit]
    return OrderEvent(
        event_id=uuid4(),
        producer_id=configuration.producer_id,
        code_version=code_version,
        config_revision=configuration.revision,
        event_time=(time_ns() if now_ns is None else now_ns) // divisor,
        order_id=uuid4(),
        amount_cents=2500,
    )


@dataclass(frozen=True)
class StreamRecord:
    topic: str
    partition: int
    offset: int
    kafka_timestamp_ms: int | None
    kafka_timestamp_type: str
    payload: bytes | None
    ingested_at: datetime


def transport_status(
    last_ingested_at: datetime | None, now: datetime | None = None
) -> str:
    if last_ingested_at is None:
        return "warming_up"
    age = ((now or datetime.now(UTC)) - last_ingested_at).total_seconds()
    return "stale" if age > 10 else "flowing"


class RevisionConflict(Exception):
    pass
